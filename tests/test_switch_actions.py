import pytest

from conftest import make_car, stub_commands


@pytest.mark.asyncio
async def test_ac_switch_calls_api(monkeypatch):
    calls = stub_commands(monkeypatch)
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"client": object(), "cars": [make_car(vin="VIN1")]}}}})()

    from custom_components.ha_opencarwings import switch as switch_mod
    entry = type("E", (), {"entry_id": "e1"})()

    added = []
    def add(entities):
        added.extend(entities)

    await switch_mod.async_setup_entry(hass, entry, add)
    sw = added[0]

    # turn on
    await sw.async_turn_on()
    assert calls[0][0] == "VIN1"
    assert calls[0][1].command_type == 3

    # turn off
    await sw.async_turn_off()
    assert calls[1][0] == "VIN1"
    assert calls[1][1].command_type == 4
