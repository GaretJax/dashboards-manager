from unittest.mock import Mock

from kiosk_agent.service import (
    render_unit,
    run_journalctl,
    stable_install_error,
)


def test_user_template_targets_default_target_and_graphical_session():
    unit = render_unit(
        scope="user",
        display=":0",
        runtime_dir="/run/user/1000",
    )

    assert "After=graphical-session.target" in unit
    assert "Wants=graphical-session.target" in unit
    assert "PartOf=graphical-session.target" in unit
    assert "WantedBy=default.target" in unit
    assert "Environment=DISPLAY=:0" in unit
    assert "Environment=XDG_RUNTIME_DIR=/run/user/1000" in unit
    assert "run --config %i" in unit
    assert "kiosk-agent@.service" not in unit


def test_system_template_has_user_and_graphical_target():
    unit = render_unit(scope="system", user="kiosk")

    assert "After=graphical.target" in unit
    assert "Wants=graphical.target" in unit
    assert "User=kiosk" in unit
    assert "WantedBy=graphical.target" in unit


def test_user_journal_logs_filter_named_instance(monkeypatch):
    run = Mock()
    monkeypatch.setattr(
        "kiosk_agent.service.shutil.which", lambda _: "/bin/journalctl"
    )
    monkeypatch.setattr("kiosk_agent.service.subprocess.run", run)
    monkeypatch.setenv("SUDO_UID", "1000")

    run_journalctl("user", follow=True, lines=25, config_name="lobby")

    assert run.call_args.args[0] == [
        "journalctl",
        "_SYSTEMD_USER_UNIT=kiosk-agent@lobby.service",
        "_UID=1000",
        "--no-pager",
        "-n",
        "25",
        "-f",
    ]


def test_stable_install_error_recommends_uv_tool_install(monkeypatch):
    monkeypatch.setattr(
        "kiosk_agent.service.ephemeral_runtime_reason",
        lambda: "interpreter is in uv cache",
    )

    error = stable_install_error()

    assert error is not None
    assert "uv tool install kiosk-agent" in error
    assert stable_install_error(allow_ephemeral=True) is None
