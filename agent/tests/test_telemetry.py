from datetime import UTC, datetime
from time import monotonic
from unittest.mock import Mock

from kiosk_agent.telemetry import (
    AgentTelemetry,
    RuntimeState,
    collect_host_metrics,
    read_meminfo,
)


def test_runtime_state_reports_uptime_and_values():
    state = RuntimeState(
        agent_started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    state.update(
        health_state="healthy",
        current_content_id=12,
    )

    snapshot = state.snapshot()

    assert snapshot["health_state"] == "healthy"
    assert snapshot["current_content_id"] == 12
    assert snapshot["uptime_seconds"] >= 0


def test_screenshot_uploads_keep_duplicate_content_orders_separate():
    manager = Mock()
    telemetry = AgentTelemetry(manager, RuntimeState(), Mock())
    captured_at = datetime(2026, 1, 1, tzinfo=UTC)

    telemetry.queue_screenshot(12, 1, b"first", captured_at, "healthy")
    telemetry.queue_screenshot(12, 2, b"second", captured_at, "healthy")
    telemetry._upload_pending(  # pyright: ignore[reportPrivateUsage]
        monotonic()
    )

    assert [
        call.args[0]["order"]
        for call in manager.upload_screenshot.call_args_list
    ] == ["1", "2"]


def test_collect_host_metrics_parses_meminfo(monkeypatch):
    monkeypatch.setattr(
        "kiosk_agent.telemetry.read_meminfo",
        lambda _path: {"MemTotal": 100, "MemAvailable": 25},
    )

    metrics = collect_host_metrics()

    assert metrics["memory_total_bytes"] == 100 * 1024
    assert metrics["memory_available_bytes"] == 25 * 1024
    assert metrics["memory_used_bytes"] == 75 * 1024
    assert metrics["memory_percent"] == 75


def test_read_meminfo_ignores_invalid_lines(tmp_path):
    path = tmp_path / "meminfo"
    path.write_text("MemTotal: 100 kB\nInvalid\nBroken: nope\n")

    assert read_meminfo(path) == {"MemTotal": 100}
