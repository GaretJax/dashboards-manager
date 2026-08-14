from pathlib import Path

from kiosk_agent.paths import ensure_profile_dir, ephemeral_runtime_reason


def test_uv_cache_interpreter_is_not_service_safe():
    reason = ephemeral_runtime_reason(
        Path("/home/kiosk/.cache/uv/archive-v0/example/bin/python")
    )

    assert reason is not None
    assert "uv " in reason


def test_stable_interpreter_is_service_safe():
    assert (
        ephemeral_runtime_reason(
            Path("/home/kiosk/.local/share/uv/tools/kiosk-agent/bin/python")
        )
        is None
    )


def test_profile_directory_is_created(tmp_path):
    profile = ensure_profile_dir(tmp_path / "profile")

    assert profile.is_dir()
