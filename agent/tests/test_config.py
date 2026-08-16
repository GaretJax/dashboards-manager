import pytest

import kiosk_agent.config as config
from kiosk_agent.config import ConfigError
from kiosk_agent.paths import AgentPaths


def _paths(tmp_path):
    return AgentPaths(
        data=tmp_path / "data",
        config=tmp_path / "config",
        cache=tmp_path / "cache",
        runtime=tmp_path / "runtime",
        profile=tmp_path / "profile",
    )


def test_dump_and_load_config_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "get_paths", lambda: _paths(tmp_path))
    values = {
        "manager": "https://manager.example",
        "screen": "TOKEN",
        "cec_port": "/dev/cec0",
        "poll_interval": 15.0,
        "launch_browser": True,
        "update_interval": 21600.0,
        "auto_update": True,
        "display_identity": "HDMI-A-1",
    }

    path = config.dump_config("lobby", values)
    first = path.read_text(encoding="utf-8")
    config.dump_config("lobby", values)

    assert path == tmp_path / "config/lobby.toml"
    assert path.read_text(encoding="utf-8") == first
    assert config.load_config("lobby") == values


def test_dump_and_load_config_accepts_full_path(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "get_paths", lambda: _paths(tmp_path))
    path = tmp_path / "custom" / "lobby.toml"
    values = {
        "manager": "https://manager.example",
        "screen": "TOKEN",
    }

    written = config.dump_config(path, values)

    assert written == path
    assert config.load_config(path) == values


def test_merge_config_applies_cli_overrides(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "get_paths", lambda: _paths(tmp_path))
    config.dump_config(
        "lobby",
        {
            "manager": "https://manager.example",
            "screen": "FILE",
            "poll_interval": 20,
        },
    )

    values = config.merge_config(
        "lobby",
        {
            "screen": "CLI",
            "cec_port": "/dev/cec0",
            "event_level": "warning",
        },
    )

    assert values["screen"] == "CLI"
    assert values["event_level"] == "WARNING"
    assert values["poll_interval"] == 20
    assert values["cec_port"] == "/dev/cec0"


def test_missing_required_config_values_are_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "get_paths", lambda: _paths(tmp_path))
    config.dump_config("broken", {"manager": "https://manager.example"})

    with pytest.raises(ConfigError, match="manager and screen"):
        config.merge_config("broken", {})


def test_invalid_config_name_is_rejected():
    with pytest.raises(ConfigError, match="config name"):
        config.validate_config_name("../lobby")
