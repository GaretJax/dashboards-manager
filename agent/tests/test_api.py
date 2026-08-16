import logging

import pytest

from kiosk_agent import api
from kiosk_agent.api import ManagerClient, ManagerError


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("GET", "https://manager.example")
            response = httpx.Response(
                self.status_code, request=request, json=self.payload
            )
            raise httpx.HTTPStatusError(
                "request failed", request=request, response=response
            )

    def json(self):
        return self.payload


class RedirectClient:
    def __init__(self, location):
        self.location = location

    def head(self, url, follow_redirects):
        assert url.endswith("/downloads/kiosk-agent.whl")
        assert follow_redirects is False
        return type(
            "Response",
            (),
            {
                "status_code": 302,
                "headers": {"location": self.location},
                "raise_for_status": lambda self: None,
            },
        )()

    def close(self):
        pass


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.url = None
        self.post_url = None
        self.post_payload = None
        self.closed = False

    def get(self, url):
        self.url = url
        return self.response

    def post(self, url, json):
        self.post_url = url
        self.post_payload = json
        return self.response

    def close(self):
        self.closed = True


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeClient(
        FakeResponse(
            {
                "version": "abc",
                "desired_power_state": "on",
                "reported_power_state": "unknown",
                "pending_command": {
                    "id": "restart-1",
                    "command": "restart_agent",
                },
                "items": [
                    {
                        "url": "https://example.test/two",
                        "duration_seconds": 20,
                        "order": 2,
                        "preload_delay_seconds": 0,
                        "preload_timeout_seconds": 25,
                    },
                    {
                        "url": "https://example.test/one",
                        "duration_seconds": 10,
                        "order": 1,
                        "preload_delay_seconds": 2.5,
                        "preload_timeout_seconds": 10,
                    },
                ],
            }
        )
    )
    monkeypatch.setattr(api.httpx, "Client", lambda timeout: client)
    return client


def test_manager_client_fetches_and_orders_playlist(fake_client, caplog):
    client = ManagerClient("https://manager.example/", "token/value")

    caplog.set_level(logging.DEBUG, logger="kiosk_agent.api")
    config = client.fetch_config()

    assert "fetched config version=abc items=2" in caplog.text
    assert any(
        record.levelno == logging.DEBUG
        and "fetched config" in record.getMessage()
        for record in caplog.records
    )
    assert fake_client.url == (
        "https://manager.example/api/screens/token%2Fvalue/config"
    )
    assert config.version == "abc"
    assert [item.order for item in config.items] == [1, 2]
    assert config.items[0].preload_delay_seconds == 2.5
    assert config.items[0].preload_timeout_seconds == 10
    assert config.items[1].preload_delay_seconds == 0
    assert config.desired_power_state == "on"
    assert config.reported_power_state == "unknown"
    assert config.pending_command is not None
    assert config.pending_command.id == "restart-1"
    client.report_state("off", "restart-2")
    assert fake_client.post_url == (
        "https://manager.example/api/screens/token%2Fvalue/state"
    )
    assert fake_client.post_payload == {
        "actual_power_state": "off",
        "command_id": "restart-2",
    }
    client.close()
    assert fake_client.closed is True


def test_manager_client_resolves_relative_content_urls(monkeypatch):
    fake = FakeClient(
        FakeResponse(
            {
                "version": "abc",
                "items": [
                    {
                        "url": "/screens/token/contents/3/",
                        "duration_seconds": 10,
                        "order": 1,
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(api.httpx, "Client", lambda timeout: fake)
    client = ManagerClient("https://manager.example", "token")

    config = client.fetch_config()

    assert config.items[0].url == (
        "https://manager.example/screens/token/contents/3/"
    )
    client.close()


def test_manager_client_checks_wheel_redirect(monkeypatch):
    fake = RedirectClient("/downloads/kiosk_agent-0.1.2-py3-none-any.whl")
    monkeypatch.setattr(api.httpx, "Client", lambda timeout: fake)
    client = ManagerClient("https://manager.example", "token")

    update = client.check_agent_update()

    assert update.filename == "kiosk_agent-0.1.2-py3-none-any.whl"
    assert update.version == "0.1.2"
    assert update.url == (
        "https://manager.example/downloads/kiosk_agent-0.1.2-py3-none-any.whl"
    )
    client.close()


def test_manager_client_defaults_preload_values(monkeypatch):
    fake = FakeClient(
        FakeResponse(
            {
                "version": "abc",
                "items": [
                    {
                        "url": "https://example.test",
                        "duration_seconds": 10,
                        "order": 1,
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(api.httpx, "Client", lambda timeout: fake)
    client = ManagerClient("https://manager.example", "token")

    config = client.fetch_config()

    assert config.items[0].preload_delay_seconds == 0
    assert config.items[0].preload_timeout_seconds == 30
    client.close()


def test_manager_client_rejects_invalid_payload(monkeypatch):
    fake = FakeClient(FakeResponse({"version": "abc", "items": [{}]}))
    monkeypatch.setattr(api.httpx, "Client", lambda timeout: fake)
    client = ManagerClient("https://manager.example", "token")

    with pytest.raises(ManagerError, match="invalid configuration"):
        client.fetch_config()

    client.close()
