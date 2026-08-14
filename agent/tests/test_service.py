from pathlib import Path

from kiosk_agent.service import render_unit, stable_install_error


def test_user_unit_targets_default_target_and_graphical_session():
    unit = render_unit(
        scope="user",
        manager="https://manager.example",
        screen="TOKEN",
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        poll_interval=15,
        profile_dir=None,
        ephemeral_profile=False,
        launch_browser=True,
        display=":0",
        runtime_dir="/run/user/1000",
    )

    assert "After=graphical-session.target" in unit
    assert "Wants=graphical-session.target" in unit
    assert "PartOf=graphical-session.target" in unit
    assert "WantedBy=default.target" in unit
    assert "Environment=DISPLAY=:0" in unit
    assert "Environment=XDG_RUNTIME_DIR=/run/user/1000" in unit
    assert "--manager https://manager.example" in unit


def test_system_unit_has_user_and_graphical_target():
    unit = render_unit(
        scope="system",
        manager="https://manager.example",
        screen="TOKEN",
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        poll_interval=15,
        profile_dir=Path("/var/lib/kiosk-agent/chromium"),
        ephemeral_profile=False,
        launch_browser=False,
        user="kiosk",
    )

    assert "After=graphical.target" in unit
    assert "Wants=graphical.target" in unit
    assert "User=kiosk" in unit
    assert "WantedBy=graphical.target" in unit
    assert "--no-launch-browser" in unit


def test_stable_install_error_recommends_uv_tool_install(monkeypatch):
    monkeypatch.setattr(
        "kiosk_agent.service.ephemeral_runtime_reason",
        lambda: "interpreter is in uv cache",
    )

    error = stable_install_error()

    assert error is not None
    assert "uv tool install kiosk-agent" in error
    assert stable_install_error(allow_ephemeral=True) is None
