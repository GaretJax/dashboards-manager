import logging
import time

from .api import ManagerClient, ManagerError, PlaylistItem, ScreenConfig
from .browser import BrowserController, BrowserError

LOGGER = logging.getLogger("kiosk_agent")


class AgentRunner:
    def __init__(
        self,
        manager: ManagerClient,
        browser: BrowserController,
        poll_interval: float = 15,
    ):
        self.manager = manager
        self.browser = browser
        self.poll_interval = poll_interval

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
        next_poll = time.monotonic() + self.poll_interval

        while True:
            if not config.items:
                LOGGER.warning("screen playlist is empty")
                time.sleep(self.poll_interval)
                config = self._poll(config)
                current_index = 0
                next_poll = time.monotonic() + self.poll_interval
                continue

            item = config.items[current_index]
            self._navigate_with_recovery(item)
            deadline = time.monotonic() + item.duration_seconds
            changed = False

            while time.monotonic() < deadline:
                now = time.monotonic()
                sleep_for = min(0.5, max(0, deadline - now))
                if now >= next_poll:
                    new_config = self._poll(config)
                    next_poll = time.monotonic() + self.poll_interval
                    if new_config.version != config.version:
                        config = new_config
                        current_index = 0
                        changed = True
                        break
                    config = new_config
                time.sleep(sleep_for)

            if not changed:
                current_index = (current_index + 1) % len(config.items)

    def _poll(self, previous: ScreenConfig) -> ScreenConfig:
        try:
            return self.manager.fetch_config()
        except ManagerError as exc:
            LOGGER.warning("configuration poll failed: %s", exc)
            return previous

    def _navigate_with_recovery(self, item: PlaylistItem):
        try:
            self.browser.navigate(
                item.url,
                preload_seconds=item.preload_seconds,
                preload_timeout_seconds=item.preload_timeout_seconds,
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
                    preload_seconds=item.preload_seconds,
                    preload_timeout_seconds=item.preload_timeout_seconds,
                )
                return
            except BrowserError as exc:
                LOGGER.warning("browser recovery failed: %s", exc)
                time.sleep(5)
