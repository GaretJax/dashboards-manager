import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from attrs import define, field

from . import __version__
from .api import ManagerClient, ManagerError
from .browser import BrowserController, BrowserError
from .display import probe_display
from .events import AgentEventReporter


@define(slots=True)
class RuntimeState:
    agent_version: str = __version__
    agent_started_at: datetime = field(factory=lambda: datetime.now(UTC))
    _lock: threading.RLock = field(factory=threading.RLock, repr=False)
    _values: dict = field(factory=dict, repr=False)

    def update(self, **values):
        with self._lock:
            self._values.update(values)

    def snapshot(self) -> dict:
        with self._lock:
            values = dict(self._values)
        values.update(
            {
                "agent_version": self.agent_version,
                "agent_started_at": self.agent_started_at,
                "uptime_seconds": max(
                    0,
                    (
                        datetime.now(UTC) - self.agent_started_at
                    ).total_seconds(),
                ),
                "health_state": values.get("health_state", "unknown"),
                "health_error": values.get("health_error", ""),
            }
        )
        return values


@define(slots=True)
class _PendingScreenshot:
    content_id: int
    image: bytes
    captured_at: datetime
    health_state: str
    error_summary: str
    retry_at: float = 0
    attempts: int = 0


class AgentTelemetry:
    def __init__(
        self,
        manager: ManagerClient,
        state: RuntimeState,
        browser: BrowserController,
        status_interval: float = 60,
    ):
        self.manager = manager
        self.state = state
        self.browser = browser
        self.status_interval = status_interval
        self.events = AgentEventReporter(manager)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending: dict[int, _PendingScreenshot] = {}
        self._pending_lock = threading.RLock()

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="kiosk-telemetry",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def emit(self, code: str, level: str, message: str, **context):
        self.events.emit(code, level, message, **context)

    def queue_screenshot(
        self,
        content_id: int,
        image: bytes,
        captured_at: datetime,
        health_state: str,
        error_summary: str = "",
    ):
        if content_id <= 0:
            return
        with self._pending_lock:
            self._pending[content_id] = _PendingScreenshot(
                content_id,
                image,
                captured_at,
                health_state,
                error_summary[:2000],
            )

    def _run(self):
        next_status = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_status:
                self._report_status()
                next_status = now + self.status_interval
            self._upload_pending(now)
            self.events.flush()
            self._stop.wait(0.5)

    def _report_status(self):
        try:
            browser_version = self.browser.browser_version()
        except BrowserError as exc:
            browser_version = ""
            self.state.update(browser_error=str(exc)[:2000])
        else:
            self.state.update(browser_version=browser_version)

        display = probe_display()
        self.state.update(
            display_identity=display.identity or "",
            display_width=display.width,
            display_height=display.height,
            display_refresh_rate=display.refresh_rate,
            display_orientation=display.orientation or "",
            display_error=display.error or "",
        )
        payload = self.state.snapshot()
        payload.update(collect_host_metrics())
        for key in ("agent_started_at", "last_successful_page_load_at"):
            value = payload.get(key)
            if isinstance(value, datetime):
                payload[key] = value.isoformat().replace("+00:00", "Z")
        try:
            self.manager.report_status(payload)
        except ManagerError:
            # Status transport failures must not interrupt playback.
            return

    def _upload_pending(self, now: float):
        with self._pending_lock:
            pending = tuple(self._pending.items())
        for content_id, screenshot in pending:
            if screenshot.retry_at > now:
                continue
            try:
                self.manager.upload_screenshot(
                    {
                        "content_id": str(content_id),
                        "captured_at": screenshot.captured_at.isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "health_state": screenshot.health_state,
                        "error_summary": screenshot.error_summary,
                    },
                    screenshot.image,
                )
            except ManagerError:
                screenshot.attempts += 1
                screenshot.retry_at = now + min(
                    60, 2 ** min(screenshot.attempts, 6)
                )
                continue
            with self._pending_lock:
                current = self._pending.get(content_id)
                if current is screenshot:
                    self._pending.pop(content_id, None)


def collect_host_metrics() -> dict:
    metrics = {
        "load_1m": None,
        "load_5m": None,
        "load_15m": None,
        "memory_total_bytes": None,
        "memory_used_bytes": None,
        "memory_available_bytes": None,
        "memory_percent": None,
    }
    try:
        loads = os.getloadavg()
    except (AttributeError, OSError):
        loads = None
    if loads is not None:
        metrics.update(
            load_1m=loads[0],
            load_5m=loads[1],
            load_15m=loads[2],
        )

    try:
        meminfo = read_meminfo(Path("/proc/meminfo"))
    except OSError:
        return metrics
    total = meminfo.get("MemTotal")
    available = meminfo.get("MemAvailable")
    if total is None:
        return metrics
    available = available if available is not None else meminfo.get("MemFree")
    if available is None:
        return metrics
    total_bytes = total * 1024
    available_bytes = available * 1024
    used_bytes = max(0, total_bytes - available_bytes)
    metrics.update(
        memory_total_bytes=total_bytes,
        memory_used_bytes=used_bytes,
        memory_available_bytes=available_bytes,
        memory_percent=(used_bytes / total_bytes * 100 if total_bytes else 0),
    )
    return metrics


def read_meminfo(path: Path) -> dict[str, int]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, raw_value = line.partition(":")
        if not separator:
            continue
        parts = raw_value.strip().split()
        if not parts:
            continue
        try:
            value = int(parts[0])
        except ValueError:
            continue
        if len(parts) > 1 and parts[1].lower() == "kb":
            values[key] = value
        else:
            values[key] = value
    return values
