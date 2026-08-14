from urllib.parse import quote

import httpx
from attrs import define


class ManagerError(RuntimeError):
    """Raised when manager API cannot provide a valid playlist."""


@define(frozen=True, slots=True)
class PlaylistItem:
    url: str
    duration_seconds: float
    order: int


@define(frozen=True, slots=True)
class ScreenConfig:
    version: str
    items: tuple[PlaylistItem, ...]


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
            version = payload["version"]
            raw_items = payload["items"]
            if not isinstance(version, str) or not isinstance(raw_items, list):
                raise TypeError
            items = tuple(
                PlaylistItem(
                    str(item["url"]),
                    float(item["duration_seconds"]),
                    int(item["order"]),
                )
                for item in raw_items
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ManagerError(
                "manager returned invalid configuration"
            ) from exc

        if any(item.duration_seconds <= 0 for item in items):
            raise ManagerError("manager returned non-positive duration")

        return ScreenConfig(
            version,
            tuple(sorted(items, key=lambda item: (item.order, item.url))),
        )
