import logging
import math
from urllib.parse import quote

import httpx
from attrs import define

from .cec import PowerSchedule

LOGGER = logging.getLogger(__name__)


class ManagerError(RuntimeError):
    """Raised when manager API cannot provide a valid playlist."""


DEFAULT_PRELOAD_DELAY_SECONDS = 0.0
DEFAULT_PRELOAD_TIMEOUT_SECONDS = 30


@define(frozen=True, slots=True)
class PlaylistItem:
    url: str
    duration_seconds: float
    order: int
    preload_delay_seconds: float
    preload_timeout_seconds: float


@define(frozen=True, slots=True)
class ScreenConfig:
    version: str
    items: tuple[PlaylistItem, ...]
    on_schedule: str | None = None
    off_schedule: str | None = None


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


class ManagerClient:
    def __init__(
        self, manager_url: str, screen_token: str, timeout: float = 5
    ):
        self.manager_url = manager_url.rstrip("/")
        self.screen_token = screen_token.strip()
        self._client = httpx.Client(timeout=timeout)

    @property
    def config_url(self) -> str:
        token = quote(self.screen_token, safe="")
        return f"{self.manager_url}/api/screens/{token}/config"

    def close(self):
        self._client.close()

    def fetch_config(self) -> ScreenConfig:
        try:
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
        )
        LOGGER.info(
            "fetched config version=%s items=%d",
            config.version,
            len(config.items),
        )
        return config
