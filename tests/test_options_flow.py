import pytest

from custom_components.ha_opencarwings import config_flow as cf


class _Entries:
    def __init__(self):
        self.updated = None

    def async_update_entry(self, entry, **kwargs):
        self.updated = kwargs


def _handler():
    entry = type("E", (), {
        "entry_id": "e1",
        "data": {"username": "someone", "api_base_url": "https://carwings.example.com"},
        "options": {},
    })()
    handler = cf.OptionsFlowHandler(entry)
    handler.config_entry = entry
    handler.hass = type("H", (), {"config_entries": _Entries()})()
    handler.async_create_entry = lambda title, data: {"title": title, "data": data}
    return handler


@pytest.mark.asyncio
async def test_blank_password_saves_options_without_touching_credentials():
    handler = _handler()
    result = await handler.async_step_init({
        "username": "someone",
        "password": "",
        "scan_interval": 15,
        "api_base_url": "https://carwings.example.com",
        "command_pin": "",
        "gps_max_radius_km": 75,
    })
    # Credentials stay out of the options, and no re-authentication happened.
    assert "password" not in result["data"]
    assert "username" not in result["data"]
    assert result["data"]["gps_max_radius_km"] == 75
    assert handler.hass.config_entries.updated is None


def test_entry_title_names_the_server_then_the_account():
    assert cf._entry_title("someone", "https://carwings.example.com") == \
        "someone - carwings.example.com"
