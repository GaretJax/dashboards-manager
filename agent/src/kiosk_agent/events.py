import re
import threading
from collections import deque
from datetime import UTC, datetime

from attrs import define, field

from .api import ManagerClient, ManagerError

_EVENT_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_EVENT_LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


@define(slots=True)
class AgentEventReporter:
    manager: ManagerClient
    minimum_level: str = "DEBUG"
    _queue: deque = field(factory=lambda: deque(maxlen=100), repr=False)
    _lock: threading.RLock = field(factory=threading.RLock, repr=False)

    def __attrs_post_init__(self):
        self.minimum_level = self.minimum_level.upper()
        if self.minimum_level not in _EVENT_LEVELS:
            raise ValueError("invalid minimum event level")

    def emit(
        self,
        code: str,
        level: str,
        message: str,
        *,
        content_id: int | None = None,
        url: str | None = None,
        fingerprint: str = "",
        details: dict | None = None,
    ):
        if not _EVENT_CODE.fullmatch(code):
            raise ValueError("invalid event code")
        level = level.upper()
        if level not in _EVENT_LEVELS:
            raise ValueError("invalid event level")
        if _EVENT_LEVELS[level] < _EVENT_LEVELS[self.minimum_level]:
            return
        event = {
            "code": code,
            "level": level,
            "message": message[:500],
            "content_id": content_id,
            "url": url,
            "occurred_at": datetime.now(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "fingerprint": fingerprint[:128],
            "details": dict(details or {}),
        }
        with self._lock:
            self._queue.append(event)

    def flush(self) -> bool:
        with self._lock:
            batch = list(self._queue)[:50]
        if not batch:
            return True
        try:
            self.manager.report_events(batch)
        except ManagerError:
            return False
        with self._lock:
            for _event in batch:
                if self._queue:
                    self._queue.popleft()
        return True
