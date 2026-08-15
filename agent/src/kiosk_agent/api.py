import logging
import math
import threading
from urllib.parse import quote

import httpx
from attrs import define

from .cec import PowerSchedule

LOGGER = logging.getLogger(__name__)


class ManagerError(RuntimeError):
    """Raised when manager API cannot provide a valid playlist."""


DEFAULT_PRELOAD_DELAY_SECONDS = 0.0
DEFAULT_PRELOAD_TIMEOUT_SECONDS = 30
POWER_STATES = {"on", "off", "unknown"}
POWER_OVERRIDES = {"on", "off"}
RESTART_AGENT_COMMAND = "restart_agent"


@define(frozen=True, slots=True)
class PlaylistItem:
    url: str
    duration_seconds: float
    order: int
    preload_delay_seconds: float
    preload_timeout_seconds: float
    content_id: int = 0
    injected_css: str | None = None
    injected_javascript_before: str | None = None
    injected_javascript_after: str | None = None


@define(frozen=True, slots=True)
class PendingCommand:
    id: str
    command: str


@define(frozen=True, slots=True)
class ScreenConfig:
    version: str
    items: tuple[PlaylistItem, ...]
    on_schedule: str | None = None
    off_schedule: str | None = None
    power_override: str | None = None
    desired_power_state: str | None = None
    reported_power_state: str = "unknown"
    pending_command: PendingCommand | None = None


def _parse_preload_delay_seconds(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError from exc
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError
    return seconds


def _parse_preload_timeout_seconds(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError
    return seconds


def _parse_schedule(value) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError
    PowerSchedule(on_schedule=value)
    return value


def _parse_power_state(value, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or value not in POWER_STATES:
        raise ValueError
    return value


def _parse_power_override(value) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or value not in POWER_OVERRIDES:
        raise ValueError
    return value


def _parse_injection(value) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) > 65536:
        raise ValueError
    return value


def _parse_pending_command(value) -> PendingCommand | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError
    command_id = value.get("id")
    command = value.get("command")
    if (
        not isinstance(command_id, str)
        or not command_id
        or command != RESTART_AGENT_COMMAND
    ):
        raise ValueError
    return PendingCommand(command_id, command)


class ManagerClient:
    def __init__(
        self, manager_url: str, screen_token: str, timeout: float = 5
    ):
        self.manager_url = manager_url.rstrip("/")
        self.screen_token = screen_token.strip()
        self._client = httpx.Client(timeout=timeout)
        self._lock = threading.RLock()

    @property
    def config_url(self) -> str:
        token = quote(self.screen_token, safe="")
        return f"{self.manager_url}/api/screens/{token}/config"

    @property
    def state_url(self) -> str:
        token = quote(self.screen_token, safe="")
        return f"{self.manager_url}/api/screens/{token}/state"

    @property
    def status_url(self) -> str:
        token = quote(self.screen_token, safe="")
        return f"{self.manager_url}/api/screens/{token}/status"

    @property
    def screenshots_url(self) -> str:
        token = quote(self.screen_token, safe="")
        return f"{self.manager_url}/api/screens/{token}/screenshots"

    def close(self):
        with self._lock:
            self._client.close()

    def fetch_config(self) -> ScreenConfig:
        try:
            with self._lock:
                response = self._client.get(self.config_url)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ManagerError(
                f"manager returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ManagerError(f"manager request failed: {exc}") from exc

        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError
            version = payload["version"]
            raw_items = payload["items"]
            on_schedule = _parse_schedule(payload.get("on_schedule"))
            off_schedule = _parse_schedule(payload.get("off_schedule"))
            power_override = _parse_power_override(
                payload.get("power_override")
            )
            desired_power_state = _parse_power_state(
                payload.get("desired_power_state"), allow_none=True
            )
            reported_power_state = _parse_power_state(
                payload.get("reported_power_state", "unknown")
            )
            pending_command = _parse_pending_command(
                payload.get("pending_command")
            )
            if not isinstance(version, str) or not isinstance(raw_items, list):
                raise TypeError
            items = tuple(
                PlaylistItem(
                    str(item["url"]),
                    float(item["duration_seconds"]),
                    int(item["order"]),
                    _parse_preload_delay_seconds(
                        item.get(
                            "preload_delay_seconds",
                            DEFAULT_PRELOAD_DELAY_SECONDS,
                        )
                    ),
                    _parse_preload_timeout_seconds(
                        item.get(
                            "preload_timeout_seconds",
                            DEFAULT_PRELOAD_TIMEOUT_SECONDS,
                        )
                    ),
                    int(item.get("content_id", 0)),
                    _parse_injection(item.get("injected_css")),
                    _parse_injection(item.get("injected_javascript_before")),
                    _parse_injection(item.get("injected_javascript_after")),
                )
                for item in raw_items
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ManagerError(
                "manager returned invalid configuration"
            ) from exc

        if any(item.duration_seconds <= 0 for item in items):
            raise ManagerError("manager returned non-positive duration")

        config = ScreenConfig(
            version,
            tuple(sorted(items, key=lambda item: (item.order, item.url))),
            on_schedule,
            off_schedule,
            power_override,
            desired_power_state,
            reported_power_state or "unknown",
            pending_command,
        )
        LOGGER.info(
            "fetched config version=%s items=%d",
            config.version,
            len(config.items),
        )
        return config

    def report_state(
        self,
        actual_power_state: str,
        command_id: str | None = None,
    ):
        if actual_power_state not in POWER_STATES:
            raise ValueError("invalid actual power state")
        payload = {"actual_power_state": actual_power_state}
        if command_id is not None:
            payload["command_id"] = command_id
        try:
            with self._lock:
                response = self._client.post(self.state_url, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ManagerError(
                f"manager returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ManagerError(f"manager state request failed: {exc}") from exc

    def report_status(self, payload: dict):
        try:
            with self._lock:
                response = self._client.post(self.status_url, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ManagerError(
                f"manager returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ManagerError(
                f"manager status request failed: {exc}"
            ) from exc

    def upload_screenshot(self, payload: dict, image: bytes):
        try:
            with self._lock:
                response = self._client.post(
                    self.screenshots_url,
                    data=payload,
                    files={"image": ("screenshot.png", image, "image/png")},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ManagerError(
                f"manager returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ManagerError(
                f"manager screenshot request failed: {exc}"
            ) from exc
