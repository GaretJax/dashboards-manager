from pathlib import Path

import kiosk_agent.display as display_module
from kiosk_agent.display import (
    detect_display_backend,
    display_environment_detail,
    display_environment_ready,
    probe_display,
    runtime_directory,
)


def test_detects_wayland_and_requires_runtime_directory():
    environment = {
        "WAYLAND_DISPLAY": "wayland-0",
        "XDG_RUNTIME_DIR": "/run/user/1000",
    }

    assert detect_display_backend(environment) == "wayland"
    assert display_environment_ready(environment)
    assert display_environment_detail(environment) == (
        "Wayland (WAYLAND_DISPLAY=wayland-0, XDG_RUNTIME_DIR=/run/user/1000)"
    )


def test_defaults_runtime_directory_from_platformdirs(monkeypatch):
    monkeypatch.setattr(
        display_module,
        "get_runtime_dir",
        lambda: Path("/run/user/1000"),
    )
    environment = {"WAYLAND_DISPLAY": "wayland-0"}

    assert runtime_directory(environment) == "/run/user/1000"
    assert display_environment_ready(environment)
    assert "XDG_RUNTIME_DIR=/run/user/1000 (default)" in (
        display_environment_detail(environment)
    )


def test_detects_x11():
    environment = {"DISPLAY": ":0"}

    assert detect_display_backend(environment) == "x11"
    assert display_environment_ready(environment)
    assert display_environment_detail(environment) == "X11 (DISPLAY=:0)"


def test_suggests_display_environment_variables_when_missing():
    environment = {}

    assert detect_display_backend(environment) is None
    assert not display_environment_ready(environment)
    assert "DISPLAY" in display_environment_detail(environment)
    assert "WAYLAND_DISPLAY" in display_environment_detail(environment)
    assert "XDG_RUNTIME_DIR" in display_environment_detail(environment)


def test_probes_wayland_output(monkeypatch):
    monkeypatch.setattr(
        display_module.shutil, "which", lambda command: command
    )
    monkeypatch.setattr(
        display_module.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "HDMI-A-1 enabled 2560x1440@59.95Hz normal",
                "stderr": "",
            },
        )(),
    )

    info = probe_display({"WAYLAND_DISPLAY": "wayland-0"})

    assert info.identity == "HDMI-A-1"
    assert info.width == 2560
    assert info.height == 1440
    assert info.refresh_rate == 59.95
    assert info.orientation == "normal"


def test_wayland_takes_precedence_over_x11():
    environment = {
        "DISPLAY": ":0",
        "WAYLAND_DISPLAY": "wayland-0",
        "XDG_RUNTIME_DIR": "/run/user/1000",
    }

    assert detect_display_backend(environment) == "wayland"
