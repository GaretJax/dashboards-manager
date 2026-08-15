import logging
import time

from .api import ManagerClient, ManagerError, PlaylistItem, ScreenConfig
from .browser import BrowserController, BrowserError
from .cec import CecController, CecError

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
    ):
        self.manager = manager
        self.browser = browser
        self.poll_interval = poll_interval
        self.cec = cec
        self._power_state: str | None = None
        self._last_reported_power_state: str | None = None

    def run(self):
        try:
            config = self.manager.fetch_config()
            self.browser.start()
            self._run_playlist(config)
        finally:
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
            return self.manager.fetch_config()
        except ManagerError as exc:
            LOGGER.warning("configuration poll failed: %s", exc)
            return previous

    def _activate_with_recovery(self, item: PlaylistItem, key: str):
        try:
            self.browser.activate_preload(key)
            return
        except BrowserError as exc:
            LOGGER.warning("preloaded navigation failed: %s", exc)
        self._navigate_with_recovery(item)

    def _navigate_with_recovery(self, item: PlaylistItem):
        try:
            self.browser.navigate(
                item.url,
                preload_delay_seconds=item.preload_delay_seconds,
                preload_timeout_seconds=item.preload_timeout_seconds,
                injected_css=item.injected_css,
                injected_javascript_before=item.injected_javascript_before,
                injected_javascript_after=item.injected_javascript_after,
            )
            return
        except BrowserError as exc:
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
                return
            except BrowserError as exc:
                LOGGER.warning("browser recovery failed: %s", exc)
                time.sleep(5)
