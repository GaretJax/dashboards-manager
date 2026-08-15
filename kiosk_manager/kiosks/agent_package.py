from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class AgentPackageError(ImproperlyConfigured):
    """The packaged agent wheel is unavailable or ambiguous."""


def agent_wheel_path() -> Path:
    wheel_dir = Path(settings.KIOSK_AGENT_WHEEL_DIR)
    wheels = sorted(
        path
        for path in wheel_dir.glob("*.whl")
        if path.is_file() and path.name.startswith("kiosk_agent-")
    )
    if len(wheels) != 1:
        raise AgentPackageError(
            f"expected one kiosk-agent wheel in {wheel_dir}, found {len(wheels)}"
        )
    return wheels[0]
