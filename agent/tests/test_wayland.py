from pathlib import Path
from unittest.mock import Mock

import pytest

import kiosk_agent.wayland as wayland
from kiosk_agent.wayland import WaylandSetupError


def test_render_labwc_keybindings_contains_cursor_binding():
    rendered = wayland.render_labwc_keybindings()

    assert 'key="W-A-F8"' in rendered
    assert '<action name="HideCursor" />' in rendered
    assert "VirtualOutputAdd" not in rendered
    assert "MoveToOutput" not in rendered


def test_install_labwc_keybindings_preserves_existing_config(tmp_path):
    path = tmp_path / "rc.xml"
    path.write_text(
        '<labwc_config><keyboard><keybind key="W-A-F1" /></keyboard>'
        "</labwc_config>",
        encoding="utf-8",
    )

    wayland.install_labwc_keybindings(path)
    updated = path.read_text(encoding="utf-8")

    assert "W-A-F1" in updated
    assert updated.count("kiosk-agent-cursor:start") == 1
    assert "HideCursor" in updated


def test_install_labwc_keybindings_removes_legacy_offscreen_block(tmp_path):
    path = tmp_path / "rc.xml"
    path.write_text(
        "<labwc_config><keyboard>"
        "<!-- kiosk-agent-pre-render:start -->old"
        "<!-- kiosk-agent-pre-render:end -->"
        "</keyboard></labwc_config>",
        encoding="utf-8",
    )

    wayland.install_labwc_keybindings(path)
    updated = path.read_text(encoding="utf-8")

    assert "kiosk-agent-pre-render" not in updated
    assert "kiosk-agent-cursor:start" in updated


def test_install_labwc_keybindings_replaces_managed_block(tmp_path):
    path = tmp_path / "rc.xml"
    path.write_text(
        "<labwc_config>"
        "<!-- kiosk-agent-cursor:start -->old"
        "<!-- kiosk-agent-cursor:end -->"
        "</labwc_config>",
        encoding="utf-8",
    )

    wayland.install_labwc_keybindings(path)
    updated = path.read_text(encoding="utf-8")

    assert "old" not in updated
    assert updated.count("kiosk-agent-cursor:start") == 1


def test_hide_cursor_presses_labwc_binding(monkeypatch):
    run = Mock()
    monkeypatch.setattr(wayland.subprocess, "run", run)
    monkeypatch.setattr(wayland, "_tool", lambda name: f"/usr/bin/{name}")

    wayland.hide_cursor()

    assert run.call_args.args[0] == [
        "/usr/bin/wtype",
        "-M",
        "logo",
        "-M",
        "alt",
        "-k",
        "F8",
        "-m",
        "alt",
        "-m",
        "logo",
    ]


def test_labwc_pid_uses_configured_pid(monkeypatch, tmp_path):
    process = tmp_path / "123"
    process.mkdir()
    (process / "comm").write_text("labwc\n", encoding="utf-8")
    monkeypatch.setenv("LABWC_PID", "123")
    monkeypatch.setattr(
        Path,
        "stat",
        lambda _path: Mock(st_uid=0),
    )
    monkeypatch.setattr(wayland.os, "getuid", lambda: 0)

    assert wayland._labwc_pid(tmp_path) == 123  # pyright: ignore[reportPrivateUsage]


def test_labwc_pid_rejects_invalid_configured_pid(monkeypatch, tmp_path):
    monkeypatch.setenv("LABWC_PID", "bad")

    with pytest.raises(WaylandSetupError, match="not a valid PID"):
        wayland._labwc_pid(tmp_path)  # pyright: ignore[reportPrivateUsage]
