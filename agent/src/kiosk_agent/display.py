import os
from collections.abc import Mapping
from typing import Literal

from .paths import get_runtime_dir

DisplayBackend = Literal["wayland", "x11"]


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
