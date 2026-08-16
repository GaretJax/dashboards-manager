from unittest.mock import Mock

import pytest

from kiosk_agent import __version__
from kiosk_agent.api import PendingCommand, PlaylistItem, ScreenConfig
from kiosk_agent.runner import AgentRestartRequested, AgentRunner
from kiosk_agent.update import AgentUpdate


def _item(url, duration, preload_delay=0):
    return PlaylistItem(
        url=url,
        duration_seconds=duration,
        order=0,
        preload_delay_seconds=preload_delay,
        preload_timeout_seconds=30,
    )


def test_runner_uses_configured_event_level():
    runner = AgentRunner(Mock(), Mock(), event_level="INFO")

    assert runner.telemetry.events.minimum_level == "INFO"


def test_new_agent_update_installs_and_requests_service_restart(monkeypatch):
    manager = Mock()
    manager.check_agent_update.return_value = AgentUpdate(
        "kiosk_agent-0.3.0-py3-none-any.whl",
        "https://manager.example/downloads/kiosk_agent-0.3.0-py3-none-any.whl",
        "0.3.0",
    )
    manager.download_agent_wheel.return_value = b"wheel"
    runner = AgentRunner(manager, Mock(), config_name="kiosk")
    verify_wheel = Mock()
    monkeypatch.setattr("kiosk_agent.runner.verify_wheel", verify_wheel)
    monkeypatch.setattr("kiosk_agent.runner.install_wheel", Mock())
    monkeypatch.setattr("kiosk_agent.runner.refresh_service", Mock())
    restart = Mock()
    monkeypatch.setattr("kiosk_agent.runner.run_systemctl", restart)

    with pytest.raises(AgentRestartRequested):
        runner._maybe_update()  # pyright: ignore[reportPrivateUsage]

    manager.check_agent_update.assert_called_once_with()
    manager.download_agent_wheel.assert_called_once()
    assert (
        verify_wheel.call_args.args[0].name
        == manager.check_agent_update.return_value.filename
    )
    restart.assert_called_once()
    events = [
        event
        for batch in manager.report_events.call_args_list
        for event in batch.args[0]
    ]
    assert any(event["code"] == "update_installed" for event in events)
    update_started = next(
        event for event in events if event["code"] == "update_started"
    )
    assert update_started["level"] == "INFO"
    assert update_started["details"] == {
        "from_version": __version__,
        "to_version": "0.3.0",
    }


def test_remote_upgrade_command_installs_and_acknowledges(monkeypatch):
    manager = Mock()
    manager.check_agent_update.return_value = AgentUpdate(
        "kiosk_agent-0.3.0-py3-none-any.whl",
        "https://manager.example/downloads/kiosk_agent-0.3.0-py3-none-any.whl",
        "0.3.0",
    )
    manager.download_agent_wheel.return_value = b"wheel"
    runner = AgentRunner(
        manager,
        Mock(),
        auto_update=False,
        config_name="kiosk",
    )
    monkeypatch.setattr("kiosk_agent.runner.verify_wheel", Mock())
    monkeypatch.setattr("kiosk_agent.runner.install_wheel", Mock())
    monkeypatch.setattr("kiosk_agent.runner.refresh_service", Mock())
    config = ScreenConfig(
        version="version",
        items=(),
        pending_command=PendingCommand("upgrade-1", "upgrade_agent"),
    )

    with pytest.raises(AgentRestartRequested):
        runner._sync_power(config)  # pyright: ignore[reportPrivateUsage]

    manager.report_state.assert_called_once_with("unknown", "upgrade-1")
    assert any(
        event["code"] == "update_started"
        for batch in manager.report_events.call_args_list
        for event in batch.args[0]
    )


def test_numeric_preloads_start_before_scheduled_display():
    browser = Mock()
    runner = AgentRunner(Mock(), browser)
    config = ScreenConfig(
        version="version",
        items=(
            _item("https://current.example", 10),
            _item("https://next.example", 10, 5),
            _item("https://far.example", 10, 25),
        ),
    )
    pending = set()

    runner._schedule_preloads(  # pyright: ignore[reportPrivateUsage]
        config,
        current_index=0,
        current_position=0,
        display_started=100,
        pending=pending,
        now=100,
    )

    assert pending == {"version-2"}
    browser.start_preload.assert_called_once_with(
        "version-2",
        "https://far.example",
        30,
        25.0,
        None,
        None,
        None,
    )

    runner._schedule_preloads(  # pyright: ignore[reportPrivateUsage]
        config,
        current_index=0,
        current_position=0,
        display_started=100,
        pending=pending,
        now=105,
    )

    assert pending == {"version-1", "version-2"}
    assert browser.start_preload.call_args_list[-1].args == (
        "version-1",
        "https://next.example",
        30,
        5.0,
        None,
        None,
        None,
    )


def test_navigation_always_preloads_with_numeric_delay():
    browser = Mock()
    runner = AgentRunner(Mock(), browser)
    item = _item("https://example.test", 10, 7)

    runner._navigate_with_recovery(  # pyright: ignore[reportPrivateUsage]
        item
    )

    browser.navigate.assert_called_once_with(
        item.url,
        preload_delay_seconds=7,
        preload_timeout_seconds=30,
        injected_css=None,
        injected_javascript_before=None,
        injected_javascript_after=None,
    )


def test_remote_power_state_sends_on_command_once():
    cec = Mock()
    manager = Mock()
    runner = AgentRunner(manager, Mock(), cec=cec)
    config = ScreenConfig(
        version="version",
        items=(),
        desired_power_state="on",
    )

    runner._sync_power(config)  # pyright: ignore[reportPrivateUsage]
    runner._sync_power(config)  # pyright: ignore[reportPrivateUsage]

    cec.set_power.assert_called_once_with("on")
    manager.report_state.assert_called_once_with("on", None)


def test_remote_power_state_maps_off_to_standby():
    cec = Mock()
    manager = Mock()
    runner = AgentRunner(manager, Mock(), cec=cec)
    config = ScreenConfig(
        version="version",
        items=(),
        desired_power_state="off",
    )

    runner._sync_power(config)  # pyright: ignore[reportPrivateUsage]

    cec.set_power.assert_called_once_with("standby")
    manager.report_state.assert_called_once_with("off", None)


def test_restart_command_is_acknowledged_before_exit():
    manager = Mock()
    runner = AgentRunner(manager, Mock())
    config = ScreenConfig(
        version="version",
        items=(),
        pending_command=PendingCommand("restart-1", "restart_agent"),
    )

    with pytest.raises(AgentRestartRequested):
        runner._sync_power(config)  # pyright: ignore[reportPrivateUsage]

    manager.report_state.assert_called_once_with("unknown", "restart-1")
