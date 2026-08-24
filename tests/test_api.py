import pytest

import asyncio

from custom_components.ha_opencarwings import api


class MockResponse:
    def __init__(self, status=200, json_data=None, text_data=""):
        self.status = status
        self._json = json_data or {}
        self._text = text_data

    async def json(self):
        return self._json

    async def text(self):
        return self._text


class MockSession:
    def __init__(self):
        self.requests = []
        self.calls = []

    async def request(self, method, url, headers=None, **kwargs):
        self.calls.append((method, url, headers or {}))
        # return the next queued request response if present
        if self.requests:
            return self.requests.pop(0)
        return MockResponse(200, {"ok": True})


def _client(monkeypatch, session):
    monkeypatch.setattr(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        lambda hass: session,
    )
    return api.OpenCarWingsAPI(hass=None)


@pytest.mark.asyncio
async def test_api_key_goes_in_the_authorization_header(monkeypatch):
    session = MockSession()
    client = _client(monkeypatch, session)
    client.set_api_key("abc123")

    await client.async_request("GET", "/api/car/")

    assert session.calls[0][2]["Authorization"] == "Token abc123"


@pytest.mark.asyncio
async def test_request_without_key_sends_no_authorization(monkeypatch):
    session = MockSession()
    client = _client(monkeypatch, session)

    await client.async_request("GET", "/api/car/")

    assert "Authorization" not in session.calls[0][2]


@pytest.mark.asyncio
async def test_validate_api_key_success(monkeypatch):
    session = MockSession()
    session.requests.append(MockResponse(200, [{"vin": "VIN1"}]))
    client = _client(monkeypatch, session)
    client.set_api_key("abc123")

    cars = await client.async_validate_api_key()

    assert cars[0]["vin"] == "VIN1"


@pytest.mark.asyncio
async def test_validate_api_key_rejected(monkeypatch):
    session = MockSession()
    session.requests.append(MockResponse(401, {}, "unauthorized"))
    client = _client(monkeypatch, session)
    client.set_api_key("wrong")

    with pytest.raises(api.AuthenticationError):
        await client.async_validate_api_key()


@pytest.mark.asyncio
async def test_validate_without_a_key_fails_before_any_request(monkeypatch):
    session = MockSession()
    client = _client(monkeypatch, session)

    with pytest.raises(api.AuthenticationError):
        await client.async_validate_api_key()

    assert session.calls == []


@pytest.mark.asyncio
async def test_blank_key_is_treated_as_no_key(monkeypatch):
    session = MockSession()
    client = _client(monkeypatch, session)
    client.set_api_key("   ")

    assert client._api_key is None


@pytest.mark.asyncio
async def test_get_car_by_vin_unauthorized(monkeypatch):
    session = MockSession()
    session.requests.append(MockResponse(403, {}, "forbidden"))
    client = _client(monkeypatch, session)
    client.set_api_key("abc123")

    with pytest.raises(api.AuthenticationError):
        await client.async_get_car_by_vin("VIN1")


@pytest.mark.asyncio
async def test_request_network_error(monkeypatch):
    class BadSession(MockSession):
        async def request(self, method, url, headers=None, **kwargs):
            raise Exception("network")

    client = _client(monkeypatch, BadSession())
    with pytest.raises(api.RequestError):
        await client.async_request("GET", "/api/car/")
