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


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.url = None
        self.closed = False

    def get(self, url):
        self.url = url
        return self.response

    def close(self):
        self.closed = True


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeClient(
        FakeResponse(
            {
                "version": "abc",
                "on_schedule": "DTSTART:20260101T080000Z\nRRULE:FREQ=DAILY",
                "off_schedule": None,
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

    caplog.set_level(logging.INFO, logger="kiosk_agent.api")
    config = client.fetch_config()

    assert "fetched config version=abc items=2" in caplog.text
    assert fake_client.url == (
        "https://manager.example/api/screens/token%2Fvalue/config"
    )
    assert config.version == "abc"
    assert [item.order for item in config.items] == [1, 2]
    assert config.items[0].preload_delay_seconds == 2.5
    assert config.items[0].preload_timeout_seconds == 10
    assert config.items[1].preload_delay_seconds == 0
    assert config.on_schedule is not None
    assert config.off_schedule is None
    client.close()
    assert fake_client.closed is True


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
