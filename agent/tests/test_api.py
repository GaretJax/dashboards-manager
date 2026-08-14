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
                "items": [
                    {
                        "url": "https://example.test/two",
                        "duration_seconds": 20,
                        "order": 2,
                        "preload_seconds": "auto",
                        "preload_timeout_seconds": 25,
                    },
                    {
                        "url": "https://example.test/one",
                        "duration_seconds": 10,
                        "order": 1,
                        "preload_seconds": 2.5,
                        "preload_timeout_seconds": 10,
                    },
                ],
            }
        )
    )
    monkeypatch.setattr(api.httpx, "Client", lambda timeout: client)
    return client


def test_manager_client_fetches_and_orders_playlist(fake_client):
    client = ManagerClient("https://manager.example/", "token/value")

    config = client.fetch_config()

    assert fake_client.url == (
        "https://manager.example/api/screens/token%2Fvalue/config"
    )
    assert config.version == "abc"
    assert [item.order for item in config.items] == [1, 2]
    assert config.items[0].preload_seconds == 2.5
    assert config.items[0].preload_timeout_seconds == 10
    assert config.items[1].preload_seconds == "auto"
    assert config.items[1].preload_timeout_seconds == 25
    client.close()
    assert fake_client.closed is True


def test_manager_client_rejects_invalid_payload(monkeypatch):
    fake = FakeClient(FakeResponse({"version": "abc", "items": [{}]}))
    monkeypatch.setattr(api.httpx, "Client", lambda timeout: fake)
    client = ManagerClient("https://manager.example", "token")

    with pytest.raises(ManagerError, match="invalid configuration"):
        client.fetch_config()

    client.close()
