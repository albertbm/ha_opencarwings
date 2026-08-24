import importlib

import pytest

module = importlib.import_module("custom_components.ha_opencarwings")


class _Entries:
    def __init__(self):
        self.updated = None

    def async_update_entry(self, entry, **kwargs):
        self.updated = kwargs
        if "data" in kwargs:
            entry.data = kwargs["data"]
        if "version" in kwargs:
            entry.version = kwargs["version"]


def _hass():
    return type("H", (), {"data": {}, "config_entries": _Entries()})()


@pytest.mark.asyncio
async def test_migration_drops_username_and_tokens():
    hass = _hass()
    entry = type("E", (), {
        "entry_id": "e1",
        "title": "someone - carwings.example.com",
        "version": 1,
        "data": {
            "username": "someone",
            "access_token": "a",
            "refresh_token": "r",
            "api_base_url": "https://carwings.example.com",
            "scan_interval": 15,
        },
    })()

    assert await module.async_migrate_entry(hass, entry) is True

    data = hass.config_entries.updated["data"]
    assert data["api_key"] == ""
    assert "username" not in data
    assert "access_token" not in data
    assert "refresh_token" not in data
    # Unrelated settings survive the migration.
    assert data["scan_interval"] == 15
    assert hass.config_entries.updated["version"] == 2


@pytest.mark.asyncio
async def test_migration_leaves_current_entries_alone():
    hass = _hass()
    entry = type("E", (), {"entry_id": "e1", "title": "t", "version": 2, "data": {"api_key": "k"}})()

    assert await module.async_migrate_entry(hass, entry) is True
    assert hass.config_entries.updated is None


@pytest.mark.asyncio
async def test_setup_without_an_api_key_asks_for_reauth():
    hass = _hass()
    entry = type("E", (), {"entry_id": "e1", "title": "t", "data": {"api_key": ""}})()

    with pytest.raises(module.ConfigEntryAuthFailed):
        await module.async_setup_entry(hass, entry)
