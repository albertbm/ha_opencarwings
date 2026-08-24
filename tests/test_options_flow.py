import pytest

from custom_components.ha_opencarwings import config_flow as cf
from custom_components.ha_opencarwings.api import AuthenticationError


class MockClient:
    def __init__(self, hass=None, base_url=None, api_key=None):
        self.api_key = api_key

    async def async_validate_api_key(self):
        if self.api_key == "good":
            return []
        raise AuthenticationError("bad key")


class _Entries:
    def __init__(self):
        self.updated = None

    def async_update_entry(self, entry, **kwargs):
        self.updated = kwargs


def _handler():
    entry = type("E", (), {
        "entry_id": "e1",
        "data": {"api_key": "old", "api_base_url": "https://carwings.example.com"},
        "options": {},
    })()
    handler = cf.OptionsFlowHandler(entry)
    handler.config_entry = entry
    handler.hass = type("H", (), {"config_entries": _Entries()})()
    handler.async_create_entry = lambda title, data: {"title": title, "data": data}
    return handler


@pytest.mark.asyncio
async def test_blank_api_key_saves_options_without_touching_credentials():
    handler = _handler()
    result = await handler.async_step_init({
        "api_key": "",
        "scan_interval": 15,
        "api_base_url": "https://carwings.example.com",
        "command_pin": "",
        "gps_max_radius_km": 75,
    })
    # A blank key never lands in the options and leaves the stored one alone.
    assert "api_key" not in result["data"]
    assert result["data"]["gps_max_radius_km"] == 75
    assert handler.hass.config_entries.updated is None


@pytest.mark.asyncio
async def test_new_api_key_is_validated_and_stored(monkeypatch):
    monkeypatch.setattr(cf, "OpenCarWingsAPI", MockClient)
    handler = _handler()

    result = await handler.async_step_init({
        "api_key": "good",
        "scan_interval": 15,
        "api_base_url": "https://carwings.example.com",
        "command_pin": "",
        "gps_max_radius_km": 0,
    })

    assert "api_key" not in result["data"]
    assert handler.hass.config_entries.updated["data"]["api_key"] == "good"


@pytest.mark.asyncio
async def test_rejected_api_key_shows_an_error(monkeypatch):
    monkeypatch.setattr(cf, "OpenCarWingsAPI", MockClient)
    handler = _handler()
    handler.async_show_form = lambda **kwargs: {"type": "form", **kwargs}

    result = await handler.async_step_init({
        "api_key": "bad",
        "scan_interval": 15,
        "api_base_url": "https://carwings.example.com",
        "command_pin": "",
        "gps_max_radius_km": 0,
    })

    assert result["type"] == "form"
    assert "base" in result.get("errors", {})
    assert handler.hass.config_entries.updated is None


def test_entry_title_names_the_server():
    assert cf._entry_title("https://carwings.example.com") == "OpenCARWINGS - carwings.example.com"
