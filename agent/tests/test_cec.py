from unittest.mock import Mock

import pytest

import kiosk_agent.cec as cec
from kiosk_agent.cec import CecController, CecError


def test_cec_power_command_matches_expected_protocol(monkeypatch):
    run = Mock(return_value=Mock(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(cec.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cec.subprocess, "run", run)

    CecController("/dev/cec0").set_power("on")
    CecController("/dev/cec0").set_power("standby")

    assert run.call_args_list[0].args[0] == [
        "/usr/bin/cec-client",
        "-s",
        "-d",
        "1",
        "/dev/cec0",
    ]
    assert run.call_args_list[0].kwargs["input"] == "on 0\n"
    assert run.call_args_list[1].kwargs["input"] == "standby 0\n"


def test_cec_power_rejects_unknown_state():
    with pytest.raises(CecError, match="unsupported CEC power state"):
        CecController("/dev/cec0").set_power("unknown")


def test_list_cec_ports_parses_cec_client_output(monkeypatch):
    monkeypatch.setattr(cec.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        cec.subprocess,
        "run",
        lambda *args, **kwargs: Mock(
            returncode=0,
            stdout="com port: /dev/cec0\ncom port: /dev/cec1\n",
            stderr="",
        ),
    )

    assert cec.list_cec_ports() == ["/dev/cec0", "/dev/cec1"]
