import logging
from unittest.mock import Mock

from click.testing import CliRunner

from kiosk_agent import cli
from kiosk_agent import config as config_module
from kiosk_agent.cli import main
from kiosk_agent.paths import AgentPaths


def test_module_cli_exposes_version():
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "0.1.1" in result.output


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
            "left",
            "--manager",
            "https://manager.example",
            "--screen",
            "TOKEN",
            "--no-enable",
            "--no-start",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "config/left.toml").exists()
    install.assert_called_once()
    assert install.call_args.args[-1] == "left"


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
