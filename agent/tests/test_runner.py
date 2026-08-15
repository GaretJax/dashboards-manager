from unittest.mock import Mock

from kiosk_agent.api import PlaylistItem, ScreenConfig
from kiosk_agent.runner import AgentRunner


def _item(url, duration, preload_delay=0):
    return PlaylistItem(
        url=url,
        duration_seconds=duration,
        order=0,
        preload_delay_seconds=preload_delay,
        preload_timeout_seconds=30,
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
        "version-2", "https://far.example", 30, 25.0
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
    )


def test_power_schedule_sends_on_command_once():
    cec = Mock()
    runner = AgentRunner(Mock(), Mock(), cec=cec)
    config = ScreenConfig(
        version="version",
        items=(),
        on_schedule="DTSTART:20000101T000000Z\nRRULE:FREQ=DAILY",
    )

    runner._sync_power(config)  # pyright: ignore[reportPrivateUsage]
    runner._sync_power(config)  # pyright: ignore[reportPrivateUsage]

    cec.set_power.assert_called_once_with("on")
