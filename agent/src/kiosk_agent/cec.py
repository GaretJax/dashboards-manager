import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from attrs import define, field
from dateutil.rrule import rrulestr

CEC_CLIENT = "cec-client"
CEC_ON = "on 0"
CEC_STANDBY = "standby 0"
_CEC_PORT_PATTERN = re.compile(r"/dev/cec[\w.-]*")


class CecError(RuntimeError):
    """Raised when HDMI-CEC cannot be queried or controlled."""


def find_cec_client(command: str | None = None) -> str:
    executable = shutil.which(command or CEC_CLIENT)
    if executable:
        return executable
    raise CecError(
        "cec-client not found; install cec-utils or configure another client"
    )


def _run_client(
    args: list[str],
    *,
    input_text: str | None = None,
    check: bool = True,
    command: str | None = None,
) -> subprocess.CompletedProcess:
    executable = find_cec_client(command)
    try:
        result = subprocess.run(  # noqa: S603
            [executable, *args],
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise CecError(f"could not run cec-client: {exc}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise CecError(f"cec-client failed: {detail}")
    return result


def list_cec_ports(command: str | None = None) -> list[str]:
    result = _run_client(["-l"], command=command)
    output = f"{result.stdout}\n{result.stderr}"
    ports = sorted(set(_CEC_PORT_PATTERN.findall(output)))
    if ports:
        return ports
    return sorted(str(path) for path in Path("/dev").glob("cec*"))


def detect_cec_ports(command: str | None = None) -> list[str]:
    try:
        ports = list_cec_ports(command)
    except CecError:
        ports = []
    if ports:
        return ports
    return sorted(str(path) for path in Path("/dev").glob("cec*"))


@define(frozen=True, slots=True)
class CecController:
    port: str
    command: str | None = None

    def set_power(self, state: str):
        if state == "on":
            command = CEC_ON
        elif state == "standby":
            command = CEC_STANDBY
        else:
            raise CecError(f"unsupported CEC power state: {state}")
        _run_client(
            ["-s", "-d", "1", self.port],
            input_text=f"{command}\n",
            command=self.command,
        )


@define(frozen=True, slots=True)
class PowerSchedule:
    on_schedule: str | None = None
    off_schedule: str | None = None
    _on_rule: object | None = field(init=False, default=None)
    _off_rule: object | None = field(init=False, default=None)

    def __attrs_post_init__(self):
        object.__setattr__(self, "_on_rule", _parse_rule(self.on_schedule))
        object.__setattr__(self, "_off_rule", _parse_rule(self.off_schedule))

    def desired_state(self, now: datetime | None = None) -> str | None:
        current = now or datetime.now(UTC)
        events = []
        for state, rule in (
            ("on", self._on_rule),
            ("standby", self._off_rule),
        ):
            if rule is None:
                continue
            occurrence = rule.before(current, inc=True)
            if occurrence is not None:
                events.append((occurrence, state))
        if not events:
            return None
        return max(events, key=lambda event: event[0])[1]


def _parse_rule(value: str | None):
    if not value:
        return None
    try:
        return rrulestr(value, forceset=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid power schedule RRULE") from exc
