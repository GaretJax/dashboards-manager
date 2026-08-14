from click.testing import CliRunner

from kiosk_agent.cli import main


def test_module_cli_exposes_version():
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "0.1.1" in result.output


def test_show_unit_command_prints_unit():
    result = CliRunner().invoke(
        main,
        [
            "service",
            "show-unit",
            "--manager",
            "https://manager.example",
            "--screen",
            "TOKEN",
        ],
    )

    assert result.exit_code == 0
    assert "[Unit]" in result.output
    assert "ExecStart=" in result.output
    assert "kiosk_agent" in result.output
