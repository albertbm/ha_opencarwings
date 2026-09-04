import pytest

from conftest import run_executor, stub_client
import asyncio

import importlib
module = importlib.import_module("custom_components.ha_opencarwings")


@pytest.mark.asyncio
async def test_forward_entry_setups_and_unload(monkeypatch):
    calls = {}

    async def async_forward_entry_setups(self, entry, platforms):
        calls['forward'] = (entry, platforms)

    async def async_unload_platforms(self, entry, platforms):
        calls['unload'] = (entry, platforms)
        return True

    # hass stub with config_entries having the methods
    config_entries = type("C", (), {
        "async_forward_entry_setups": async_forward_entry_setups,
        "async_unload_platforms": async_unload_platforms,
        "async_start_reauth": lambda x: None,
    })()

    hass = type("H", (), {"data": {}, "config_entries": config_entries})()
    hass.async_add_executor_job = run_executor

    entry = type("E", (), {"entry_id": "e1", "data": {"api_key": "k"}, "title": "t"})()

    stub_client(monkeypatch)

    ok = await module.async_setup_entry(hass, entry)
    assert ok is True
    assert 'forward' in calls
    assert calls['forward'][1] == module.PLATFORMS

    # Now unload
    res = await module.async_unload_entry(hass, entry)
    assert res is True
    assert 'unload' in calls
    assert calls['unload'][1] == module.PLATFORMS
