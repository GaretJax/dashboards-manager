from unittest.mock import Mock

from kiosk_agent.events import AgentEventReporter


def test_event_reporter_filters_events_below_minimum_level():
    manager = Mock()
    reporter = AgentEventReporter(manager, minimum_level="WARNING")

    reporter.emit("loading", "DEBUG", "ignored")
    reporter.emit("page_loaded", "INFO", "ignored")
    reporter.emit("navigation_failed", "WARNING", "reported")
    reporter.flush()

    events = manager.report_events.call_args.args[0]
    assert [event["code"] for event in events] == ["navigation_failed"]


def test_event_reporter_batches_and_flushes_events():
    manager = Mock()
    reporter = AgentEventReporter(manager)

    reporter.emit(
        "navigation_failed",
        "WARNING",
        "navigation failed",
        content_id=12,
        url="https://example.com",
        details={"retry_count": 1},
    )
    reporter.flush()

    manager.report_events.assert_called_once()
    events = manager.report_events.call_args.args[0]
    assert events[0]["code"] == "navigation_failed"
    assert events[0]["content_id"] == 12
    assert events[0]["details"] == {"retry_count": 1}
