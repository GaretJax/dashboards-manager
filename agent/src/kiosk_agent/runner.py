import logging
import time
from datetime import UTC, datetime

from .api import ManagerClient, ManagerError, PlaylistItem, ScreenConfig
from .browser import BrowserController, BrowserError
from .cec import CecController, CecError
from .telemetry import AgentTelemetry, RuntimeState

LOGGER = logging.getLogger("kiosk_agent")


class AgentRestartRequested(RuntimeError):
    """Raised after manager acknowledges a one-shot restart command."""


class AgentRunner:
    def __init__(
        self,
        manager: ManagerClient,
        browser: BrowserController,
        poll_interval: float = 15,
        cec: CecController | None = None,
        status_interval: float = 60,
        screenshot_interval: float = 300,
        display_identity: str | None = None,
    ):
        self.manager = manager
        self.browser = browser
        self.poll_interval = poll_interval
        self.cec = cec
        self.status_interval = status_interval
        self.screenshot_interval = screenshot_interval
        self._power_state: str | None = None
        self._last_reported_power_state: str | None = None
        self.runtime_state = RuntimeState()
        self.telemetry = AgentTelemetry(
            manager,
            self.runtime_state,
            browser,
            status_interval=status_interval,
            display_identity=display_identity,
        )
        self._last_screenshot_at: dict[int, float] = {}

    def run(self):
        self.telemetry.start()
        self.telemetry.emit("agent_started", "INFO", "Agent started")
        try:
            config = self.manager.fetch_config()
            self.telemetry.emit(
                "config_fetched",
                "INFO",
                "Initial screen configuration fetched",
            )
            self.runtime_state.update(
                health_state="loading",
                desired_power_state=config.desired_power_state or "",
            )
            self.browser.start()
            self._run_playlist(config)
        finally:
            self.telemetry.stop()
            self.browser.close()
            self.manager.close()

    def _run_playlist(self, config: ScreenConfig):
        current_index = 0
        current_position = 0
        next_poll = time.monotonic() + self.poll_interval
        pending: set[str] = set()

        while True:
            self._sync_power(config)
            if not config.items:
                self.runtime_state.update(
                    health_state="degraded",
                    health_error="screen playlist is empty",
                    current_content_id=None,
                )
                self.telemetry.emit(
                    "healthy",
                    "WARNING",
                    "Screen playlist is empty",
                    fingerprint="empty_playlist",
                )
                LOGGER.warning("screen playlist is empty")
                self.browser.cancel_preloads()
                pending.clear()
                time.sleep(self.poll_interval)
                config = self._poll(config)
                current_index = 0
                current_position = 0
                next_poll = time.monotonic() + self.poll_interval
                continue

            item = config.items[current_index]
            preload_key = self._preload_key(config, current_position)
            if preload_key in pending:
                pending.remove(preload_key)
                self._activate_with_recovery(item, preload_key)
            else:
                self._navigate_with_recovery(item)
            display_started = time.monotonic()
            deadline = display_started + item.duration_seconds
            changed = False

            while time.monotonic() < deadline:
                now = time.monotonic()
                self._sync_power(config)
                self.browser.handle_pending_dialogs()
                self._maybe_capture_screenshot(item)
                self._schedule_preloads(
                    config,
                    current_index,
                    current_position,
                    display_started,
                    pending,
                    now,
                )
                sleep_for = min(0.5, max(0, deadline - now))
                if now >= next_poll:
                    new_config = self._poll(config)
                    next_poll = time.monotonic() + self.poll_interval
                    if new_config.version != config.version:
                        self.browser.cancel_preloads()
                        pending.clear()
                        config = new_config
                        current_index = 0
                        current_position = 0
                        changed = True
                        break
                    config = new_config
                time.sleep(sleep_for)

            if not changed:
                current_index += 1
                current_position += 1
                if current_index >= len(config.items):
                    current_index = 0

    @staticmethod
    def _preload_key(config: ScreenConfig, position: int) -> str:
        return f"{config.version[:12]}-{position}"

    def _sync_power(self, config: ScreenConfig):
        desired_state = config.desired_power_state
        if (
            desired_state in {"on", "off"}
            and self.cec is not None
            and desired_state != self._power_state
        ):
            cec_state = "on" if desired_state == "on" else "standby"
            try:
                self.cec.set_power(cec_state)
            except CecError as exc:
                LOGGER.warning(
                    "CEC power command failed state=%s port=%s: %s",
                    desired_state,
                    self.cec.port,
                    exc,
                )
                self.runtime_state.update(
                    health_state="degraded",
                    health_error=str(exc),
                )
                self.telemetry.emit(
                    "display_control_failed",
                    "WARNING",
                    "CEC power command failed",
                    details={"state": desired_state},
                )
            else:
                self._power_state = desired_state
                LOGGER.info(
                    "CEC power state changed state=%s port=%s",
                    desired_state,
                    self.cec.port,
                )

        if self.cec is None:
            actual_state = "unknown"
        else:
            actual_state = self._power_state or config.reported_power_state
        self.runtime_state.update(
            desired_power_state=desired_state or "",
            actual_power_state=actual_state,
        )
        pending = config.pending_command
        if actual_state == self._last_reported_power_state and pending is None:
            return
        try:
            self.manager.report_state(
                actual_state,
                pending.id if pending is not None else None,
            )
        except ManagerError as exc:
            LOGGER.warning("power state report failed: %s", exc)
            return
        self._last_reported_power_state = actual_state
        if pending is not None:
            LOGGER.info(
                "manager restart command acknowledged id=%s", pending.id
            )
            raise AgentRestartRequested

    def _record_page_result(self, item: PlaylistItem):
        if self.browser.last_navigation_loaded:
            self.runtime_state.update(
                current_content_id=item.content_id or None,
                last_successful_page_load_at=datetime.now(UTC),
                health_state="healthy",
                health_error="",
                browser_error="",
            )
            self.telemetry.emit(
                "page_loaded",
                "INFO",
                "Content loaded successfully",
                content_id=item.content_id or None,
                url=item.url,
            )
            return
        self.runtime_state.update(
            current_content_id=item.content_id or None,
            health_state="degraded",
            health_error="readiness timeout",
            browser_error="readiness timeout",
        )
        self.telemetry.emit(
            "readiness_timeout",
            "WARNING",
            "Content did not become ready before timeout",
            content_id=item.content_id or None,
            url=item.url,
        )

    def _maybe_capture_screenshot(self, item: PlaylistItem):
        content_id = item.content_id
        if content_id <= 0 or not self.browser.last_navigation_loaded:
            return
        now = time.monotonic()
        previous = self._last_screenshot_at.get(content_id)
        if previous is not None and now - previous < self.screenshot_interval:
            return
        try:
            image = self.browser.capture_screenshot()
        except BrowserError as exc:
            LOGGER.warning("screenshot capture failed: %s", exc)
            self.runtime_state.update(
                health_state="degraded",
                health_error=str(exc),
                browser_error=str(exc),
            )
            return
        self._last_screenshot_at[content_id] = now
        snapshot = self.runtime_state.snapshot()
        self.telemetry.queue_screenshot(
            content_id,
            image,
            datetime.now(UTC),
            snapshot.get("health_state", "unknown"),
            snapshot.get("health_error", ""),
        )

    def _schedule_preloads(
        self,
        config: ScreenConfig,
        current_index: int,
        current_position: int,
        display_started: float,
        pending: set[str],
        now: float,
    ):
        due = display_started
        item_count = len(config.items)
        for offset in range(1, item_count):
            previous = config.items[(current_index + offset - 1) % item_count]
            due += previous.duration_seconds
            index = (current_index + offset) % item_count
            item = config.items[index]
            if due - item.preload_delay_seconds > now:
                continue
            position = current_position + offset
            key = self._preload_key(config, position)
            if key in pending:
                continue
            pending.add(key)
            self.telemetry.emit(
                "preloading",
                "DEBUG",
                "Content preload started",
                content_id=item.content_id or None,
                url=item.url,
            )
            self.browser.start_preload(
                key,
                item.url,
                item.preload_timeout_seconds,
                item.preload_delay_seconds,
                item.injected_css,
                item.injected_javascript_before,
                item.injected_javascript_after,
            )
            LOGGER.info(
                "scheduled preload url=%s lead_seconds=%.1f",
                item.url,
                max(0, due - now),
            )

    def _poll(self, previous: ScreenConfig) -> ScreenConfig:
        try:
            config = self.manager.fetch_config()
            self.telemetry.emit(
                "config_fetched",
                "INFO",
                "Screen configuration fetched",
            )
            return config
        except ManagerError as exc:
            self.telemetry.emit(
                "config_fetch_failed",
                "WARNING",
                "Screen configuration fetch failed",
                fingerprint="config_fetch_failed",
            )
            LOGGER.warning("configuration poll failed: %s", exc)
            return previous

    def _activate_with_recovery(self, item: PlaylistItem, key: str):
        try:
            self.browser.activate_preload(key)
            self._record_page_result(item)
            return
        except BrowserError as exc:
            LOGGER.warning("preloaded navigation failed: %s", exc)
        self._navigate_with_recovery(item)

    def _navigate_with_recovery(self, item: PlaylistItem):
        content_id = item.content_id or None
        self.telemetry.emit(
            "loading",
            "DEBUG",
            "Content navigation started",
            content_id=content_id,
            url=item.url,
        )
        try:
            self.browser.navigate(
                item.url,
                preload_delay_seconds=item.preload_delay_seconds,
                preload_timeout_seconds=item.preload_timeout_seconds,
                injected_css=item.injected_css,
                injected_javascript_before=item.injected_javascript_before,
                injected_javascript_after=item.injected_javascript_after,
            )
            self._record_page_result(item)
            return
        except BrowserError as exc:
            self.telemetry.emit(
                "navigation_failed",
                "WARNING",
                "Content navigation failed",
                content_id=content_id,
                url=item.url,
                details={"error": str(exc)[:200]},
            )
            LOGGER.warning("browser navigation failed: %s", exc)

        self.browser.close()
        while True:
            try:
                self.browser.start()
                self.browser.navigate(
                    item.url,
                    preload_delay_seconds=item.preload_delay_seconds,
                    preload_timeout_seconds=item.preload_timeout_seconds,
                    injected_css=item.injected_css,
                    injected_javascript_before=item.injected_javascript_before,
                    injected_javascript_after=item.injected_javascript_after,
                )
                self._record_page_result(item)
                return
            except BrowserError as exc:
                LOGGER.warning("browser recovery failed: %s", exc)
                time.sleep(5)
