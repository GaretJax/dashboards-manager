import contextlib
import json
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
    _message_id: int = field(init=False, default=0)

    def start(self):
        if self.launch:
            self._launch_browser()
        target = self._wait_for_page()
        try:
            self._socket = websocket.create_connection(
                target["webSocketDebuggerUrl"],
                timeout=5,
            )
        except (KeyError, OSError, websocket.WebSocketException) as exc:
            raise BrowserError(
                f"could not connect to Chrome CDP: {exc}"
            ) from exc
        self._send_command("Page.enable")

    def close(self):
        if self._socket is not None:
            with contextlib.suppress(websocket.WebSocketException):
                self._socket.close()
            self._socket = None
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired as exc:
                del exc
                self._process.kill()
                self._process.wait()
        self._process = None

    def navigate(self, url: str):
        if self._socket is None:
            raise BrowserError("browser CDP connection is not open")
        self._send_command("Page.navigate", {"url": url})

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

    def _wait_for_page(self) -> dict:
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
                    if target.get("type") == "page":
                        return target
                last_error = "CDP returned no page target"
            except (httpx.HTTPError, ValueError) as exc:
                last_error = str(exc)
            time.sleep(0.2)
        raise BrowserError(f"timed out waiting for Chrome CDP: {last_error}")

    def _send_command(self, method: str, params: dict | None = None):
        if self._socket is None:
            raise BrowserError("browser CDP connection is not open")
        self._message_id += 1
        message_id = self._message_id
        try:
            self._socket.send(
                json.dumps(
                    {
                        "id": message_id,
                        "method": method,
                        "params": params or {},
                    }
                )
            )
            while True:
                message = json.loads(self._socket.recv())
                if message.get("id") != message_id:
                    continue
                if "error" in message:
                    raise BrowserError(str(message["error"]))
                return message.get("result", {})
        except (OSError, ValueError, websocket.WebSocketException) as exc:
            self._socket = None
            raise BrowserError(f"CDP command failed: {exc}") from exc
