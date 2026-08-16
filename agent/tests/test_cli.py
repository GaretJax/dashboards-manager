import logging
from unittest.mock import Mock

from click.testing import CliRunner

from kiosk_agent import cli
from kiosk_agent import config as config_module
from kiosk_agent.cli import main
from kiosk_agent.diagnostics import CheckResult
from kiosk_agent.paths import AgentPaths
from kiosk_agent.update import AgentUpdate


def test_module_cli_exposes_version():
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "0.2.1" in result.output


def test_httpx_request_logs_are_demoted_to_debug():
    record = logging.LogRecord(
        "httpx",
        logging.INFO,
        __file__,
        1,
        "HTTP Request: %s %s %s",
        ("GET", "https://manager.example", "200 OK"),
        None,
    )

    filter_name = "_HttpxRequestLogFilter"
    log_filter = getattr(cli, filter_name)()
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)
    try:
        assert log_filter.filter(record) is True
    finally:
        root_logger.setLevel(original_level)

    assert record.levelno == logging.DEBUG
    assert record.levelname == "DEBUG"


def test_service_install_dry_run_prints_unit_without_installing(monkeypatch):
    install = Mock()
    monkeypatch.setattr(cli, "install_unit", install)

    result = CliRunner().invoke(
        main,
        [
            "service",
            "install",
            "--manager",
            "https://manager.example",
            "--screen",
            "TOKEN",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "[Service]" in result.output
    assert "ExecStart=" in result.output
    install.assert_not_called()


def test_service_install_writes_named_config_and_template(
    monkeypatch, tmp_path
):
    install = Mock()
    monkeypatch.setattr(cli, "install_unit", install)
    monkeypatch.setattr(
        config_module,
        "get_paths",
        lambda: AgentPaths(
            tmp_path / "data",
            tmp_path / "config",
            tmp_path / "cache",
            tmp_path / "runtime",
            tmp_path / "profile",
        ),
    )

    result = CliRunner().invoke(
        main,
        [
            "service",
            "install",
            "--config",
            str(tmp_path / "config" / "left.toml"),
            "--manager",
            "https://manager.example",
            "--screen",
            "TOKEN",
            "--no-enable",
            "--no-start",
        ],
    )

    assert result.exit_code == 0, result.output
    config_path = tmp_path / "config" / "left.toml"
    assert config_path.exists()
    install.assert_called_once()
    assert install.call_args.args[-1] == config_path


def test_upgrade_installs_wheel_without_screen_and_restarts_services(
    monkeypatch,
):
    client = Mock()
    client.check_agent_update.return_value = AgentUpdate(
        "kiosk_agent-0.3.0-py3-none-any.whl",
        "https://manager.example/downloads/kiosk_agent-0.3.0-py3-none-any.whl",
        "0.3.0",
    )
    client.download_agent_wheel.return_value = b"wheel"
    monkeypatch.setattr(cli, "ManagerClient", Mock(return_value=client))
    monkeypatch.setattr(cli, "verify_wheel", Mock())
    monkeypatch.setattr(cli, "install_wheel", Mock())
    monkeypatch.setattr(
        cli,
        "installed_service_instances",
        lambda _scope: ["kiosk-agent@lobby.service"],
    )
    restart = Mock()
    monkeypatch.setattr(cli, "run_systemctl", restart)

    result = CliRunner().invoke(
        main,
        ["upgrade", "--manager", "https://manager.example"],
    )

    assert result.exit_code == 0, result.output
    assert "upgraded=0.3.0" in result.output
    cli.ManagerClient.assert_called_once_with("https://manager.example")
    restart.assert_called_once_with(
        "user", "restart", "kiosk-agent@lobby.service"
    )


def test_upgrade_check_does_not_install(monkeypatch):
    client = Mock()
    client.check_agent_update.return_value = AgentUpdate(
        "kiosk_agent-0.3.0-py3-none-any.whl",
        "https://manager.example/downloads/kiosk_agent-0.3.0-py3-none-any.whl",
        "0.3.0",
    )
    monkeypatch.setattr(cli, "ManagerClient", Mock(return_value=client))
    install = Mock()
    monkeypatch.setattr(cli, "install_wheel", install)

    result = CliRunner().invoke(
        main,
        ["upgrade", "--manager", "https://manager.example", "--check"],
    )

    assert result.exit_code == 0, result.output
    assert "state=available" in result.output
    client.download_agent_wheel.assert_not_called()
    install.assert_not_called()


def test_upgrade_can_skip_service_restart(monkeypatch):
    client = Mock()
    client.check_agent_update.return_value = AgentUpdate(
        "kiosk_agent-0.3.0-py3-none-any.whl",
        "https://manager.example/downloads/kiosk_agent-0.3.0-py3-none-any.whl",
        "0.3.0",
    )
    client.download_agent_wheel.return_value = b"wheel"
    monkeypatch.setattr(cli, "ManagerClient", Mock(return_value=client))
    monkeypatch.setattr(cli, "verify_wheel", Mock())
    monkeypatch.setattr(cli, "install_wheel", Mock())
    monkeypatch.setattr(
        cli,
        "installed_service_instances",
        lambda _scope: ["kiosk-agent@lobby.service"],
    )
    restart = Mock()
    monkeypatch.setattr(cli, "run_systemctl", restart)

    result = CliRunner().invoke(
        main,
        [
            "upgrade",
            "--manager",
            "https://manager.example",
            "--no-restart",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "services not restarted" in result.output
    restart.assert_not_called()


def test_bootstrap_non_interactive_writes_config_and_service(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        config_module,
        "get_paths",
        lambda: AgentPaths(
            tmp_path / "data",
            tmp_path / "config",
            tmp_path / "cache",
            tmp_path / "runtime",
            tmp_path / "profile",
        ),
    )
    monkeypatch.setattr(
        cli,
        "_bootstrap_display",
        lambda **_kwargs: {
            "display": None,
            "wayland_display": "wayland-0",
            "runtime_dir": "/run/user/1000",
            "display_identity": "HDMI-A-1",
            "backend": "wayland",
        },
    )
    monkeypatch.setattr(cli, "_bootstrap_browser", lambda *_args: "chromium")
    monkeypatch.setattr(cli, "_bootstrap_cec", lambda *_args: None)
    monkeypatch.setattr(cli, "install_unit", Mock())
    monkeypatch.setattr(
        cli,
        "run_checks",
        lambda **_kwargs: [CheckResult("bootstrap", "ok", "ready")],
    )

    config_file = tmp_path / "config/kiosk.toml"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "bootstrap",
            "--manager",
            "https://manager.example",
            "--screen",
            "TOKEN",
            "--config",
            str(config_file),
            "--non-interactive",
        ],
    )
    retry = runner.invoke(
        main,
        [
            "bootstrap",
            "--manager",
            "https://manager.example",
            "--screen",
            "TOKEN",
            "--config",
            str(config_file),
            "--non-interactive",
        ],
    )

    assert result.exit_code == 0, result.output
    assert retry.exit_code == 0, retry.output
    config = config_file.read_text()
    assert 'manager = "https://manager.example"' in config
    assert 'screen = "TOKEN"' in config
    assert 'wayland_display = "wayland-0"' in config


def test_bootstrap_non_interactive_rejects_ambiguous_displays(monkeypatch):
    monkeypatch.setattr(
        cli,
        "current_display_environment",
        lambda: {
            "display": None,
            "wayland_display": "wayland-0",
            "runtime_dir": "/run/user/1000",
        },
    )
    monkeypatch.setattr(
        cli,
        "display_identities",
        lambda _environment: ("HDMI-A-1", "DP-1"),
    )

    result = CliRunner().invoke(
        main,
        [
            "bootstrap",
            "--manager",
            "https://manager.example",
            "--screen",
            "TOKEN",
            "--non-interactive",
        ],
    )

    assert result.exit_code != 0
    assert "multiple choices for display output" in result.output


def test_wayland_setup_dry_run_prints_cursor_binding():
    result = CliRunner().invoke(main, ["wayland", "setup", "--dry-run"])

    assert result.exit_code == 0
    assert "--- " in result.output
    assert 'keybind key="W-A-F8"' in result.output
    assert '<action name="HideCursor" />' in result.output


def test_show_unit_command_prints_unit():
    result = CliRunner().invoke(
        main,
        [
            "service",
            "show-unit",
        ],
    )

    assert result.exit_code == 0
    assert "[Unit]" in result.output
    assert "ExecStart=" in result.output
    assert "kiosk_agent" in result.output
    assert "--config %i" in result.output


def test_cec_detect_command_prints_ports(monkeypatch):
    monkeypatch.setattr(cli, "detect_cec_ports", lambda: ["/dev/cec0"])

    result = CliRunner().invoke(main, ["cec", "detect"])

    assert result.exit_code == 0
    assert result.output.strip() == "/dev/cec0"
