import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from typing import Literal

from attrs import define

from .paths import get_runtime_dir

DisplayBackend = Literal["wayland", "x11"]


@define(frozen=True, slots=True)
class DisplayInfo:
    identity: str | None = None
    width: int | None = None
    height: int | None = None
    refresh_rate: float | None = None
    orientation: str | None = None
    error: str | None = None


def detect_display_backend(
    environment: Mapping[str, str] | None = None,
) -> DisplayBackend | None:
    values = os.environ if environment is None else environment
    if values.get("WAYLAND_DISPLAY"):
        return "wayland"
    if values.get("DISPLAY"):
        return "x11"
    return None


def runtime_directory(
    environment: Mapping[str, str] | None = None,
) -> str:
    values = os.environ if environment is None else environment
    return values.get("XDG_RUNTIME_DIR") or str(get_runtime_dir())


def display_environment_ready(
    environment: Mapping[str, str] | None = None,
) -> bool:
    values = os.environ if environment is None else environment
    backend = detect_display_backend(values)
    if backend == "wayland":
        return bool(runtime_directory(values))
    return backend == "x11"


def display_identities(
    environment: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    values = os.environ if environment is None else environment
    backend = detect_display_backend(values)
    if backend is None:
        return ()
    command = "wlr-randr" if backend == "wayland" else "xrandr"
    executable = shutil.which(command)
    if executable is None:
        return ()
    try:
        result = subprocess.run(  # noqa: S603
            [executable, "--current"] if backend == "x11" else [executable],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
            env=dict(values),
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if result.returncode != 0:
        return ()
    identities = []
    for line in result.stdout.splitlines():
        match = re.match(r"^(\S+)\s+(?:connected|enabled)\b", line)
        if match and match.group(1) not in identities:
            identities.append(match.group(1))
    return tuple(identities)


def display_environment_detail(
    environment: Mapping[str, str] | None = None,
) -> str:
    values = os.environ if environment is None else environment
    backend = detect_display_backend(values)
    if backend == "wayland":
        wayland_display = values["WAYLAND_DISPLAY"]
        runtime_dir = runtime_directory(values)
        defaulted = " (default)" if not values.get("XDG_RUNTIME_DIR") else ""
        return (
            f"Wayland (WAYLAND_DISPLAY={wayland_display}, "
            f"XDG_RUNTIME_DIR={runtime_dir}{defaulted})"
        )
    if backend == "x11":
        return f"X11 (DISPLAY={values['DISPLAY']})"
    return (
        "not detected; set DISPLAY for X11, or set WAYLAND_DISPLAY "
        "and XDG_RUNTIME_DIR for Wayland"
    )


def _parse_display_output(
    output: str,
    *,
    preferred_identity: str | None = None,
) -> DisplayInfo:
    lines = output.splitlines()
    candidates = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\S+)\s+(?:connected|enabled)\b(.*)$", line)
        if match:
            candidates.append((index, match.group(1), match.group(2)))
    if not candidates:
        for index, line in enumerate(lines):
            match = re.match(r"^(\S+)\s+.*?(\d{3,5})x(\d{3,5})", line)
            if match:
                candidates.append((index, match.group(1), line))
    if not candidates:
        return DisplayInfo(error="display query returned no active output")
    selected = next(
        (
            candidate
            for candidate in candidates
            if candidate[1] == preferred_identity
        ),
        candidates[0],
    )
    index, identity, _detail = selected
    block = "\n".join(lines[index : index + 8])
    mode = re.search(r"(\d{3,5})x(\d{3,5})", block)
    if mode is None:
        return DisplayInfo(
            identity=identity, error="active display mode unavailable"
        )
    refresh_match = re.search(
        r"@(?P<at>\d+(?:\.\d+)?)\s*(?:Hz)?"
        r"|\d+x\d+\s+(?P<mode>\d+(?:\.\d+)?)",
        block,
    )
    orientation_match = re.search(
        r"\b(normal|left|right|inverted)\b", block, re.IGNORECASE
    )
    try:
        width = int(mode.group(1))
        height = int(mode.group(2))
        refresh_rate = None
        if refresh_match is not None:
            refresh_value = refresh_match.group("at") or refresh_match.group(
                "mode"
            )
            refresh_rate = float(refresh_value)
    except (TypeError, ValueError, OverflowError):
        return DisplayInfo(identity=identity, error="invalid display mode")
    return DisplayInfo(
        identity=identity,
        width=width,
        height=height,
        refresh_rate=refresh_rate,
        orientation=(
            orientation_match.group(1).lower()
            if orientation_match is not None
            else None
        ),
    )


def probe_display(
    environment: Mapping[str, str] | None = None,
    preferred_identity: str = "HDMI-A-1",
) -> DisplayInfo:
    values = os.environ if environment is None else environment
    backend = detect_display_backend(values)
    if backend is None:
        return DisplayInfo(error="display backend unavailable")
    command = "wlr-randr" if backend == "wayland" else "xrandr"
    executable = shutil.which(command)
    if executable is None:
        return DisplayInfo(error=f"{command} not found")
    try:
        result = subprocess.run(  # noqa: S603
            [executable, "--current"] if backend == "x11" else [executable],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
            env=dict(values),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return DisplayInfo(error=f"display query failed: {exc}")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        return DisplayInfo(error=f"display query failed: {detail}")
    return _parse_display_output(
        result.stdout,
        preferred_identity=preferred_identity,
    )
