from zipfile import ZipFile

import pytest

from kiosk_agent.update import (
    AgentUpdate,
    UpdateError,
    compare_versions,
    parse_wheel_location,
    verify_wheel,
)


def test_parse_wheel_location_requires_same_manager_download_path():
    update = parse_wheel_location(
        "https://manager.example/base/downloads/kiosk-agent.whl",
        "/base/downloads/kiosk_agent-0.1.2-py3-none-any.whl",
    )

    assert update.version == "0.1.2"
    assert update.url.endswith("kiosk_agent-0.1.2-py3-none-any.whl")

    with pytest.raises(UpdateError, match="unsafe"):
        parse_wheel_location(
            "https://manager.example/downloads/kiosk-agent.whl",
            "https://evil.example/kiosk_agent-0.1.2-py3-none-any.whl",
        )


def test_compare_versions_uses_pep440():
    assert compare_versions("0.1.1", "0.1.2") == 1
    assert compare_versions("0.1.2", "0.1.2") == 0
    assert compare_versions("0.1.3", "0.1.2") == -1


def test_verify_wheel_checks_metadata(tmp_path):
    path = tmp_path / "kiosk_agent-0.1.2-py3-none-any.whl"
    with ZipFile(path, "w") as wheel:
        wheel.writestr(
            "kiosk_agent-0.1.2.dist-info/METADATA",
            "Name: kiosk-agent\nVersion: 0.1.2\nRequires-Python: >=3.11\n",
        )
        wheel.writestr(
            "kiosk_agent-0.1.2.dist-info/WHEEL",
            "Wheel-Version: 1.0\nTag: py3-none-any\n",
        )

    verify_wheel(
        path,
        AgentUpdate(path.name, "https://manager.example/download", "0.1.2"),
    )

    with pytest.raises(UpdateError, match="version"):
        verify_wheel(
            path,
            AgentUpdate(
                path.name, "https://manager.example/download", "0.1.3"
            ),
        )
