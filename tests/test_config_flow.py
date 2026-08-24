import pytest

from custom_components.ha_opencarwings.config_flow import OpenCARWINGSConfigFlow
from custom_components.ha_opencarwings import config_flow as cfg
from custom_components.ha_opencarwings.api import AuthenticationError


class MockClient:
    def __init__(self, hass=None, base_url=None, api_key=None):
        self.base_url = base_url
        self.api_key = api_key

    async def async_validate_api_key(self):
        if self.api_key == "good":
            return []
        raise AuthenticationError("bad key")


@pytest.mark.asyncio
async def test_config_flow_success(monkeypatch):
    monkeypatch.setattr(cfg, "OpenCarWingsAPI", MockClient)

    flow = OpenCARWINGSConfigFlow()
    result = await flow.async_step_user({"api_key": "good", "api_base_url": "https://custom.example"})

    assert result["type"] == "create_entry"
    assert result["data"]["api_key"] == "good"
    assert result["data"]["api_base_url"] == "https://custom.example"
    # None of the old credential keys survive.
    assert "username" not in result["data"]
    assert "access_token" not in result["data"]


@pytest.mark.asyncio
async def test_config_flow_scan_interval_selected(monkeypatch):
    monkeypatch.setattr(cfg, "OpenCarWingsAPI", MockClient)

    flow = OpenCARWINGSConfigFlow()
    # provide explicit scan_interval and ensure it's persisted
    result = await flow.async_step_user({"api_key": "good", "scan_interval": 1})

    assert result["type"] == "create_entry"
    assert result["data"]["scan_interval"] == 1


@pytest.mark.asyncio
async def test_config_flow_auth_failure(monkeypatch):
    monkeypatch.setattr(cfg, "OpenCarWingsAPI", MockClient)

    flow = OpenCARWINGSConfigFlow()
    result = await flow.async_step_user({"api_key": "bad"})

    # On auth failure, the form is shown with errors
    assert result["type"] == "form"
    assert "base" in result.get("errors", {})


class _Entries:
    def __init__(self, entry):
        self.entry = entry
        self.updated = None
        self.reloaded = None

    def async_get_entry(self, entry_id):
        return self.entry

    def async_update_entry(self, entry, **kwargs):
        self.updated = kwargs
        if "data" in kwargs:
            entry.data = kwargs["data"]

    async def async_reload(self, entry_id):
        self.reloaded = entry_id


def _reauth_flow(monkeypatch):
    monkeypatch.setattr(cfg, "OpenCarWingsAPI", MockClient)
    entry = type("E", (), {
        "entry_id": "e1",
        "data": {
            "username": "someone",
            "access_token": "a",
            "refresh_token": "r",
            "api_base_url": "https://carwings.example.com",
            "command_pin": "1234",
        },
        "options": {},
    })()
    flow = OpenCARWINGSConfigFlow()
    flow.context = {"entry_id": "e1"}
    flow.hass = type("H", (), {"config_entries": _Entries(entry)})()
    return flow, entry


@pytest.mark.asyncio
async def test_reauth_replaces_stored_credentials(monkeypatch):
    flow, entry = _reauth_flow(monkeypatch)

    await flow.async_step_reauth({})
    result = await flow.async_step_reauth_confirm({"api_key": "good"})

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    data = flow.hass.config_entries.updated["data"]
    assert data["api_key"] == "good"
    # The old sign-in is gone. Everything else survives.
    assert "username" not in data
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert data["command_pin"] == "1234"
    assert flow.hass.config_entries.reloaded == "e1"


@pytest.mark.asyncio
async def test_reauth_rejects_a_bad_key(monkeypatch):
    flow, entry = _reauth_flow(monkeypatch)

    await flow.async_step_reauth({})
    result = await flow.async_step_reauth_confirm({"api_key": "bad"})

    assert result["type"] == "form"
    assert "base" in result.get("errors", {})
    assert flow.hass.config_entries.updated is None
