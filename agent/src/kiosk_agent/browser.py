import contextlib
import json
import logging
import math
import os
import shutil
import subprocess
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
    _message_id: int = field(init=False, default=0)

    def start(self):
        if self.launch:
            self._launch_browser()
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

    def close(self):
        if self._socket is not None:
            with contextlib.suppress(websocket.WebSocketException):
                self._socket.close()
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

    def navigate(
        self,
        url: str,
        *,
        preload_seconds: bool | float | str = False,
        preload_timeout_seconds: float = 30,
    ):
        if self._socket is None:
            raise BrowserError("browser CDP connection is not open")
        if isinstance(preload_seconds, bool):
            if not preload_seconds:
                self._send_command("Page.navigate", {"url": url})
                return
            raise BrowserError(
                "preload_seconds must be false, auto, or a non-negative number"
            )
        self._preload_and_activate(
            url,
            preload_seconds,
            preload_timeout_seconds,
        )

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
                "--disable-session-crashed-bubble",
                "--no-first-run",
                "--start-maximized",
                f"--remote-debugging-address={host}",
                f"--remote-debugging-port={port}",
                f"--remote-allow-origins={origin}",
                "--password-store=basic",
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

    def _preload_and_activate(
        self,
        url: str,
        preload_seconds: float | str,
        preload_timeout_seconds: float,
    ):
        old_socket = self._socket
        old_target_id = self._target_id
        new_socket = None
        new_target_id = None
        try:
            result = self._browser_command(
                "Target.createTarget",
                {"url": "about:blank", "background": True},
            )
            new_target_id = result.get("targetId")
            if not new_target_id:
                raise BrowserError("Chrome did not return a preloading target")

            target = self._wait_for_page(new_target_id)
            new_socket = websocket.create_connection(
                target["webSocketDebuggerUrl"],
                timeout=5,
            )
            self._send_socket_command(new_socket, "Page.enable")
            self._navigate_and_wait(
                new_socket,
                url,
                preload_seconds,
                preload_timeout_seconds,
            )
            self._browser_command(
                "Target.activateTarget", {"targetId": new_target_id}
            )

            self._socket = new_socket
            self._target_id = new_target_id
            new_socket = None
            if old_socket is not None:
                with contextlib.suppress(websocket.WebSocketException):
                    old_socket.close()
            if old_target_id:
                with contextlib.suppress(BrowserError):
                    self._browser_command(
                        "Target.closeTarget", {"targetId": old_target_id}
                    )
        except (KeyError, OSError, websocket.WebSocketException) as exc:
            raise BrowserError(f"preloading failed: {exc}") from exc
        finally:
            if new_socket is not None:
                with contextlib.suppress(websocket.WebSocketException):
                    new_socket.close()
            if new_target_id and self._target_id != new_target_id:
                with contextlib.suppress(BrowserError):
                    self._browser_command(
                        "Target.closeTarget", {"targetId": new_target_id}
                    )

    def _navigate_and_wait(
        self,
        socket: websocket.WebSocket,
        url: str,
        preload_seconds: float | str,
        preload_timeout_seconds: float,
    ):
        try:
            minimum_seconds = (
                0 if preload_seconds == "auto" else float(preload_seconds)
            )
            timeout_seconds = max(
                float(preload_timeout_seconds), minimum_seconds
            )
        except (TypeError, ValueError) as exc:
            raise BrowserError(
                "preload settings must contain numeric seconds"
            ) from exc
        if (
            not math.isfinite(minimum_seconds)
            or minimum_seconds < 0
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise BrowserError("preload settings must contain valid seconds")
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
            navigation_complete = False
            load_event = False
            deadline = started + timeout_seconds
            while time.monotonic() < deadline:
                remaining = max(0.1, deadline - time.monotonic())
                socket.settimeout(min(1, remaining))
                try:
                    message = json.loads(socket.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                if message.get("method") == "Page.loadEventFired":
                    load_event = True
                if message.get("id") != navigation_id:
                    continue
                if "error" in message:
                    raise BrowserError(str(message["error"]))
                result = message.get("result") or {}
                error_text = result.get("errorText")
                if error_text:
                    raise BrowserError(f"navigation failed: {error_text}")
                navigation_complete = True
                if load_event:
                    break
            if not (navigation_complete and load_event):
                LOGGER.warning(
                    "preload timed out after %.1fs; activating %s",
                    timeout_seconds,
                    url,
                )
            else:
                remaining = started + minimum_seconds - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
        except (OSError, ValueError, websocket.WebSocketException) as exc:
            raise BrowserError(f"preload CDP command failed: {exc}") from exc
        finally:
            with contextlib.suppress(OSError, websocket.WebSocketException):
                socket.settimeout(5)

    def _wait_for_page(self, target_id: str | None = None) -> dict:
        deadline = time.monotonic() + self.startup_timeout
        url = f"{self.cdp_url.rstrip('/')}/json/list"
        last_error = "no page target"
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
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
                if message.get("id") != message_id:
                    continue
                if "error" in message:
                    raise BrowserError(str(message["error"]))
                return message.get("result", {})
        except (OSError, ValueError, websocket.WebSocketException) as exc:
            if socket is self._socket:
                self._socket = None
            raise BrowserError(f"CDP command failed: {exc}") from exc
