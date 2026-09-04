import pytest

from conftest import make_car, run_executor, stub_client

import custom_components.ha_opencarwings as module_init


def _hass():
    class C:
        async def async_forward_entry_setups(self, *args, **kwargs):
            return None

        async def async_unload_platforms(self, *args, **kwargs):
            return True

        def async_start_reauth(self, *args, **kwargs):
            return None

    hass = type("H", (), {"data": {}, "config_entries": C()})()
    hass.async_add_executor_job = run_executor
    return hass


@pytest.mark.asyncio
async def test_setup_stores_the_account_cars(monkeypatch):
    stub_client(monkeypatch, [make_car(vin="VIN1", nickname="One"),
                              make_car(vin="VIN2", nickname="Two")])
    hass = _hass()
    entry = type("E", (), {
        "entry_id": "e1",
        "data": {"api_key": "k", "api_base_url": "https://custom.example"},
        "title": "t",
    })()

    assert await module_init.async_setup_entry(hass, entry)

    stored = hass.data["ha_opencarwings"]["e1"]
    assert [c.vin for c in stored["cars"]] == ["VIN1", "VIN2"]
    assert stored["client"] is not None


@pytest.mark.asyncio
async def test_setup_without_an_api_key_asks_for_reauth(monkeypatch):
    stub_client(monkeypatch)
    entry = type("E", (), {"entry_id": "e1", "data": {}, "title": "t"})()

    with pytest.raises(module_init.ConfigEntryAuthFailed):
        await module_init.async_setup_entry(_hass(), entry)
