import contextlib
import json
import logging
import math
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import websocket
from attrs import define, field

from .display import detect_display_backend, runtime_directory

LOGGER = logging.getLogger(__name__)


class BrowserError(RuntimeError):
    """Raised when Chromium cannot be controlled."""


@define(slots=True)
class _PreloadJob:
    key: str
    url: str
    timeout_seconds: float
    preload_delay_seconds: float = 0
    injected_css: str | None = None
    injected_javascript_before: str | None = None
    injected_javascript_after: str | None = None
    target_id: str | None = None
    socket: websocket.WebSocket | None = None
    title: str | None = None
    error: BrowserError | None = None
    ready: threading.Event = field(factory=threading.Event)
    cancelled: threading.Event = field(factory=threading.Event)


def find_browser(command: str | None = None) -> str:
    candidates = [command] if command else []
    candidates.extend(["chromium", "chromium-browser", "google-chrome"])
    for candidate in candidates:
        if candidate and shutil.which(candidate):
            return candidate
    requested = command or "chromium"
    raise BrowserError(f"browser executable not found: {requested}")


@define(slots=True)
class BrowserController:
    browser: str | None
    cdp_url: str
    profile_dir: Path
    launch: bool = True
    startup_timeout: float = 20
    _process: subprocess.Popen | None = field(init=False, default=None)
    _socket: websocket.WebSocket | None = field(init=False, default=None)
    _target_id: str | None = field(init=False, default=None)
    _preload_jobs: dict[str, _PreloadJob] = field(init=False, factory=dict)
    _preload_lock: threading.RLock = field(init=False, factory=threading.RLock)
    _message_id: int = field(init=False, default=0)

    def start(self):
        if self.launch:
            self._launch_browser()
            self._wait_for_page(check_process=False)
            result = self._browser_command(
                "Target.createTarget",
                {
                    "url": "about:blank",
                    "newWindow": True,
                    "background": False,
                    "focus": True,
                    "windowState": "fullscreen",
                },
            )
            target_id = result.get("targetId")
            if not target_id:
                raise BrowserError(
                    "Chrome did not return an initial page target"
                )
            self._close_page_targets(exclude_target_id=target_id)
            target = self._wait_for_page(target_id, check_process=False)
        else:
            target = self._wait_for_page()
        try:
            socket = websocket.create_connection(
                target["webSocketDebuggerUrl"],
                timeout=5,
            )
        except (KeyError, OSError, websocket.WebSocketException) as exc:
            raise BrowserError(
                f"could not connect to Chrome CDP: {exc}"
            ) from exc
        self._socket = socket
        self._target_id = target.get("id")
        self._send_command("Page.enable")
        self._enable_focus_emulation(self._socket)

    def close(self):
        self.cancel_preloads()
        sockets = (self._socket,)
        for socket in sockets:
            if socket is not None:
                with contextlib.suppress(websocket.WebSocketException):
                    socket.close()
        self._socket = None
        self._target_id = None
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired as exc:
                del exc
                self._process.kill()
                self._process.wait()
        self._process = None

    def start_preload(
        self,
        key: str,
        url: str,
        timeout_seconds: float,
        preload_delay_seconds: float = 0,
        injected_css: str | None = None,
        injected_javascript_before: str | None = None,
        injected_javascript_after: str | None = None,
    ):
        with self._preload_lock:
            if key in self._preload_jobs:
                return
            job = _PreloadJob(
                key,
                url,
                timeout_seconds,
                preload_delay_seconds=preload_delay_seconds,
                injected_css=injected_css,
                injected_javascript_before=injected_javascript_before,
                injected_javascript_after=injected_javascript_after,
            )
            self._preload_jobs[key] = job
        threading.Thread(
            target=self._load_preload,
            args=(job,),
            name=f"kiosk-preload-{key}",
            daemon=True,
        ).start()

    def activate_preload(self, key: str):
        with self._preload_lock:
            job = self._preload_jobs.get(key)
        if job is None:
            raise BrowserError(f"preload is unavailable: {key}")

        job.ready.wait()
        with self._preload_lock:
            self._preload_jobs.pop(key, None)
        if job.error is not None:
            self._close_preload_target(job)
            raise job.error
        if job.cancelled.is_set() or job.socket is None or not job.target_id:
            self._close_preload_target(job)
            raise BrowserError(f"preload was cancelled: {key}")

        old_socket = self._socket
        old_target_id = self._target_id
        activated = False
        try:
            self._browser_command(
                "Target.activateTarget", {"targetId": job.target_id}
            )
            self._socket = job.socket
            self._target_id = job.target_id
            activated = True
        except BrowserError:
            self._close_preload_target(job)
            raise
        finally:
            if activated:
                if old_socket is not None and old_socket is not job.socket:
                    with contextlib.suppress(websocket.WebSocketException):
                        old_socket.close()
                if old_target_id and old_target_id != job.target_id:
                    with contextlib.suppress(BrowserError):
                        self._browser_command(
                            "Target.closeTarget", {"targetId": old_target_id}
                        )

    def cancel_preloads(self):
        with self._preload_lock:
            jobs = tuple(self._preload_jobs.values())
            self._preload_jobs.clear()
        for job in jobs:
            job.cancelled.set()
            self._close_preload_target(job)

    def _load_preload(self, job: _PreloadJob):
        new_socket = None
        try:
            target_id, new_socket = self._create_preload_target()
            job.target_id = target_id
            job.socket = new_socket
            self._send_socket_command(new_socket, "Page.enable")
            if job.injected_javascript_before or job.injected_javascript_after:
                self._send_socket_command(new_socket, "Runtime.enable")
            self._install_injections(
                new_socket,
                job.injected_css,
                job.injected_javascript_before,
                job.injected_javascript_after,
            )
            self._enable_focus_emulation(new_socket)
            request_started = time.monotonic()
            load_event_received = self._navigate_and_wait(
                new_socket,
                job.url,
                job.preload_delay_seconds,
                job.timeout_seconds,
            )
            if load_event_received and job.preload_delay_seconds > 0:
                timeout_remaining = max(
                    0,
                    job.timeout_seconds - (time.monotonic() - request_started),
                )
                delay = min(job.preload_delay_seconds, timeout_remaining)
                if (
                    not self._wait_with_dialogs(
                        new_socket,
                        job.cancelled,
                        delay,
                    )
                    and delay > 0
                ):
                    LOGGER.info(
                        "preload delay elapsed url=%s seconds=%.1f",
                        job.url,
                        delay,
                    )
            if not job.cancelled.is_set():
                job.ready.set()
                return
        except (
            BrowserError,
            KeyError,
            OSError,
            websocket.WebSocketException,
        ) as exc:
            job.error = (
                exc
                if isinstance(exc, BrowserError)
                else BrowserError(f"preloading failed: {exc}")
            )
        finally:
            if job.error is not None or job.cancelled.is_set():
                self._close_preload_target(job)
            job.ready.set()

    def _create_preload_target(
        self,
    ) -> tuple[str, websocket.WebSocket]:
        result = self._browser_command(
            "Target.createTarget",
            {"url": "about:blank", "background": True},
        )
        target_id = result.get("targetId")
        if not target_id:
            raise BrowserError("Chrome did not return a preload target")
        target = self._wait_for_page(target_id)
        try:
            socket = websocket.create_connection(
                target["webSocketDebuggerUrl"],
                timeout=5,
            )
        except (KeyError, OSError, websocket.WebSocketException) as exc:
            raise BrowserError(f"could not connect to preload: {exc}") from exc
        return target_id, socket

    def _close_preload_target(self, job: _PreloadJob):
        if job.socket is not None:
            with contextlib.suppress(websocket.WebSocketException):
                job.socket.close()
            job.socket = None
        if job.target_id:
            with contextlib.suppress(BrowserError):
                self._browser_command(
                    "Target.closeTarget", {"targetId": job.target_id}
                )
            job.target_id = None

    def navigate(
        self,
        url: str,
        *,
        preload_delay_seconds: float = 0,
        preload_timeout_seconds: float = 30,
        injected_css: str | None = None,
        injected_javascript_before: str | None = None,
        injected_javascript_after: str | None = None,
    ):
        if self._socket is None:
            raise BrowserError("browser CDP connection is not open")
        try:
            delay = float(preload_delay_seconds)
        except (TypeError, ValueError, OverflowError) as exc:
            raise BrowserError("preload delay must be numeric") from exc
        if not math.isfinite(delay) or delay < 0:
            raise BrowserError("preload delay must be non-negative")
        self.start_preload(
            "__direct__",
            url,
            preload_timeout_seconds,
            delay,
            injected_css,
            injected_javascript_before,
            injected_javascript_after,
        )
        self.activate_preload("__direct__")

    def _launch_browser(self):
        browser = find_browser(self.browser)
        parsed = urlparse(self.cdp_url)
        host = parsed.hostname or "127.0.0.1"
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise BrowserError("launched Chrome CDP must use localhost")
        port = parsed.port or 9222
        origin_host = parsed.netloc or f"{host}:{port}"
        origin = f"{parsed.scheme or 'http'}://{origin_host}"
        command = [browser]
        display_backend = detect_display_backend()
        environment = os.environ.copy()
        if display_backend:
            command.append(f"--ozone-platform={display_backend}")
            if display_backend == "wayland":
                environment.setdefault(
                    "XDG_RUNTIME_DIR", runtime_directory(environment)
                )
        command.extend(
            [
                "--kiosk",
                "--noerrdialogs",
                "--disable-infobars",
                "--hide-scrollbars",
                "--disable-session-crashed-bubble",
                "--no-first-run",
                "--start-maximized",
                f"--remote-debugging-address={host}",
                f"--remote-debugging-port={port}",
                f"--remote-allow-origins={origin}",
                "--password-store=basic",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                f"--user-data-dir={self.profile_dir}",
                "about:blank",
            ]
        )
        try:
            self._process = subprocess.Popen(  # noqa: S603
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=environment,
            )
        except OSError as exc:
            raise BrowserError(f"could not launch browser: {exc}") from exc

    def _close_page_targets(self, *, exclude_target_id: str):
        result = self._browser_command("Target.getTargets")
        for target in result.get("targetInfos", []):
            if target.get("type") != "page":
                continue
            target_id = target.get("targetId")
            if target_id and target_id != exclude_target_id:
                with contextlib.suppress(BrowserError):
                    self._browser_command(
                        "Target.closeTarget", {"targetId": target_id}
                    )

    def _enable_focus_emulation(self, socket: websocket.WebSocket):
        self._send_socket_command(
            socket,
            "Emulation.setFocusEmulationEnabled",
            {"enabled": True},
        )

    def _install_injections(
        self,
        socket: websocket.WebSocket,
        injected_css: str | None,
        injected_javascript_before: str | None,
        injected_javascript_after: str | None,
    ):
        if injected_css:
            try:
                self._send_socket_command(
                    socket,
                    "Page.addStyleToEvaluateOnNewDocument",
                    {"source": injected_css},
                )
            except BrowserError as exc:
                LOGGER.warning("CSS injection installation failed: %s", exc)

        if not injected_javascript_before and not injected_javascript_after:
            return
        source_parts = [
            "(() => {",
            "const run = (source, phase) => {",
            "try { (new Function(source)).call(window); }",
            "catch (error) {",
            "const detail = error && (error.stack || error.message) || String(error);",
            "console.error('[kiosk-agent-injection-error] ' + phase + ': ' + detail);",
            "}",
            "};",
        ]
        if injected_javascript_before:
            source_parts.append(
                f"run({json.dumps(injected_javascript_before)}, "
                "'javascript_before');"
            )
        if injected_javascript_after:
            source_parts.append(
                f"window.addEventListener('load', () => run({json.dumps(injected_javascript_after)}, "
                "'javascript_after'), {once: true});"
            )
        source_parts.append("})();")
        try:
            self._send_socket_command(
                socket,
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "\n".join(source_parts)},
            )
        except BrowserError as exc:
            LOGGER.warning("JavaScript injection installation failed: %s", exc)

    @staticmethod
    def _log_injection_event(message: dict):
        params = message.get("params") or {}
        for argument in params.get("args") or []:
            value = argument.get("value")
            if isinstance(value, str) and value.startswith(
                "[kiosk-agent-injection-error]"
            ):
                LOGGER.warning("%s", value)

    def _dialog_policy(self, dialog_type: str) -> bool:
        return dialog_type in {"alert", "beforeunload"}

    def _handle_dialog_event(
        self,
        socket: websocket.WebSocket,
        message: dict,
    ):
        params = message.get("params") or {}
        dialog_type = str(params.get("type") or "unknown")
        dialog_message = str(params.get("message") or "")[:200]
        accept = self._dialog_policy(dialog_type)
        LOGGER.info(
            "javascript dialog handled type=%s accept=%s message=%r",
            dialog_type,
            accept,
            dialog_message,
        )
        try:
            self._send_socket_command(
                socket,
                "Page.handleJavaScriptDialog",
                {"accept": accept},
            )
        except BrowserError as exc:
            LOGGER.warning("javascript dialog response failed: %s", exc)

    def _wait_with_dialogs(
        self,
        socket: websocket.WebSocket,
        cancelled: threading.Event,
        seconds: float,
    ) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if cancelled.is_set():
                return True
            remaining = min(0.1, max(0.01, deadline - time.monotonic()))
            socket.settimeout(remaining)
            try:
                message = json.loads(socket.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except (TypeError, ValueError):
                continue
            if message.get("method") == "Page.javascriptDialogOpening":
                self._handle_dialog_event(socket, message)
            elif message.get("method") == "Runtime.consoleAPICalled":
                self._log_injection_event(message)
        return cancelled.is_set()

    def handle_pending_dialogs(self):
        socket = self._socket
        if socket is None:
            return
        try:
            socket.settimeout(0.05)
            while True:
                try:
                    message = json.loads(socket.recv())
                except websocket.WebSocketTimeoutException:
                    return
                if message.get("method") == "Page.javascriptDialogOpening":
                    self._handle_dialog_event(socket, message)
                elif message.get("method") == "Runtime.consoleAPICalled":
                    self._log_injection_event(message)
        except (
            OSError,
            TypeError,
            ValueError,
            websocket.WebSocketException,
        ) as exc:
            LOGGER.warning("active page event drain failed: %s", exc)
        finally:
            with contextlib.suppress(OSError, websocket.WebSocketException):
                socket.settimeout(5)

    def _navigate_and_wait(
        self,
        socket: websocket.WebSocket,
        url: str,
        preload_delay_seconds: float,
        preload_timeout_seconds: float,
    ) -> bool:
        try:
            delay_seconds = float(preload_delay_seconds)
            timeout_seconds = float(preload_timeout_seconds)
        except (TypeError, ValueError, OverflowError) as exc:
            raise BrowserError(
                "preload settings must contain numeric seconds"
            ) from exc
        if (
            not math.isfinite(delay_seconds)
            or delay_seconds < 0
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise BrowserError("preload settings must contain valid seconds")
        LOGGER.info(
            "page load started url=%s preload_delay_seconds=%.1f "
            "timeout_seconds=%.1f",
            url,
            delay_seconds,
            timeout_seconds,
        )
        started = time.monotonic()
        navigation_id = self._next_message_id()
        try:
            socket.send(
                json.dumps(
                    {
                        "id": navigation_id,
                        "method": "Page.navigate",
                        "params": {"url": url},
                    }
                )
            )
            load_event = False
            deadline = started + timeout_seconds
            while time.monotonic() < deadline:
                if load_event:
                    break
                remaining = max(0.1, deadline - time.monotonic())
                socket.settimeout(min(1, remaining))
                try:
                    message = json.loads(socket.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                if message.get("method") == "Page.javascriptDialogOpening":
                    self._handle_dialog_event(socket, message)
                    continue
                if message.get("method") == "Runtime.consoleAPICalled":
                    self._log_injection_event(message)
                    continue
                if message.get("method") == "Page.loadEventFired":
                    load_event = True
                    LOGGER.info(
                        "page load event received url=%s elapsed_seconds=%.3f",
                        url,
                        time.monotonic() - started,
                    )
                    break
                if message.get("id") != navigation_id:
                    continue
                if "error" in message:
                    raise BrowserError(str(message["error"]))
                result = message.get("result") or {}
                error_text = result.get("errorText")
                if error_text:
                    raise BrowserError(f"navigation failed: {error_text}")
            if not load_event:
                LOGGER.warning(
                    "page load done url=%s result=timed_out "
                    "waiting_for=load_event timeout_seconds=%.1f",
                    url,
                    timeout_seconds,
                )
                return False
            LOGGER.info(
                "page load done url=%s result=loaded",
                url,
            )
            return True
        except (OSError, ValueError, websocket.WebSocketException) as exc:
            raise BrowserError(f"preload CDP command failed: {exc}") from exc
        finally:
            with contextlib.suppress(OSError, websocket.WebSocketException):
                socket.settimeout(5)

    def _wait_for_page(
        self,
        target_id: str | None = None,
        *,
        check_process: bool = True,
    ) -> dict:
        deadline = time.monotonic() + self.startup_timeout
        url = f"{self.cdp_url.rstrip('/')}/json/list"
        last_error = "no page target"
        while time.monotonic() < deadline:
            if (
                check_process
                and self._process is not None
                and self._process.poll() is not None
                and self._process.returncode not in (None, 0)
            ):
                raise BrowserError(
                    f"browser exited with status {self._process.returncode}"
                )
            try:
                response = httpx.get(url, timeout=1)
                response.raise_for_status()
                targets = response.json()
                for target in targets:
                    if target.get("type") != "page":
                        continue
                    if target_id is None or target.get("id") == target_id:
                        return target
                last_error = "CDP returned no matching page target"
            except (httpx.HTTPError, ValueError) as exc:
                last_error = str(exc)
            time.sleep(0.2)
        raise BrowserError(f"timed out waiting for page: {last_error}")

    def _browser_command(self, method: str, params: dict | None = None):
        try:
            response = httpx.get(
                f"{self.cdp_url.rstrip('/')}/json/version", timeout=2
            )
            response.raise_for_status()
            websocket_url = response.json()["webSocketDebuggerUrl"]
            socket = websocket.create_connection(websocket_url, timeout=5)
        except (KeyError, OSError, ValueError, httpx.HTTPError) as exc:
            raise BrowserError(
                f"could not connect to Chrome browser CDP: {exc}"
            ) from exc
        try:
            return self._send_socket_command(socket, method, params)
        finally:
            with contextlib.suppress(websocket.WebSocketException):
                socket.close()

    def _next_message_id(self) -> int:
        self._message_id += 1
        return self._message_id

    def _send_command(self, method: str, params: dict | None = None):
        if self._socket is None:
            raise BrowserError("browser CDP connection is not open")
        return self._send_socket_command(self._socket, method, params)

    def _send_socket_command(
        self,
        socket: websocket.WebSocket,
        method: str,
        params: dict | None = None,
    ):
        message_id = self._next_message_id()
        try:
            socket.send(
                json.dumps(
                    {
                        "id": message_id,
                        "method": method,
                        "params": params or {},
                    }
                )
            )
            while True:
                message = json.loads(socket.recv())
                if message.get("method") == "Page.javascriptDialogOpening":
                    self._handle_dialog_event(socket, message)
                    continue
                if message.get("method") == "Runtime.consoleAPICalled":
                    self._log_injection_event(message)
                    continue
                if message.get("id") != message_id:
                    continue
                if "error" in message:
                    raise BrowserError(str(message["error"]))
                return message.get("result", {})
        except (OSError, ValueError, websocket.WebSocketException) as exc:
            if socket is self._socket:
                self._socket = None
            raise BrowserError(f"CDP command failed: {exc}") from exc
