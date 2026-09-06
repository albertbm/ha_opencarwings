"""The paired switches send a different command each way.

Horn and lights and remote start have no state in the API, so they hold the
last command sent. Getting the off command wrong would leave the car running.
"""
import pytest

from conftest import make_car, stub_commands

from custom_components.ha_opencarwings import DOMAIN
from custom_components.ha_opencarwings import switch as switch_mod

CMD_AC_ON, CMD_AC_OFF = 3, 4
CMD_REMOTE_START, CMD_REMOTE_STOP = 11, 12
CMD_HORN_LIGHTS_ON, CMD_HORN_LIGHTS_OFF = 13, 14

FICOSA = [1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]


async def _switches(monkeypatch):
    sent = stub_commands(monkeypatch)
    car = make_car(vin="VIN1", nickname="DKL", supported_commands=FICOSA)
    hass = type("H", (), {"data": {DOMAIN: {"e1": {
        "cars": [car], "coordinator": None, "client": object()}}}})()
    hass.config_entries = type("CE", (), {"async_get_entry": staticmethod(
        lambda _: type("E", (), {"options": {}, "data": {}})())})()
    out = []
    await switch_mod.async_setup_entry(hass, type("E", (), {"entry_id": "e1"})(), out.extend)
    for s in out:
        s.hass = hass
    return {s.unique_id: s for s in out}, sent


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,on_cmd,off_cmd", [
    ("ha_opencarwings_ac_VIN1", CMD_AC_ON, CMD_AC_OFF),
    ("ha_opencarwings_cmd11_VIN1", CMD_REMOTE_START, CMD_REMOTE_STOP),
    ("ha_opencarwings_cmd13_VIN1", CMD_HORN_LIGHTS_ON, CMD_HORN_LIGHTS_OFF),
])
async def test_each_switch_sends_its_own_pair(monkeypatch, uid, on_cmd, off_cmd):
    switches, sent = await _switches(monkeypatch)
    switch = switches[uid]

    await switch.async_turn_on()
    await switch.async_turn_off()

    assert [r.command_type for _, r in sent] == [on_cmd, off_cmd]
    assert [vin for vin, _ in sent] == ["VIN1", "VIN1"]


@pytest.mark.asyncio
async def test_a_command_switch_holds_the_last_command_sent(monkeypatch):
    """The API reports no state for these, so the switch is assumed-state."""
    switches, _ = await _switches(monkeypatch)
    switch = switches["ha_opencarwings_cmd13_VIN1"]

    await switch.async_turn_on()
    assert switch.is_on is True

    await switch.async_turn_off()
    assert switch.is_on is False


@pytest.mark.asyncio
async def test_a_continental_car_gets_no_paired_switches(monkeypatch):
    """Those commands are Ficosa only, and the server rejects the rest."""
    stub_commands(monkeypatch)
    car = make_car(vin="VIN1", supported_commands=[1, 2, 3, 4, 5])
    hass = type("H", (), {"data": {DOMAIN: {"e1": {
        "cars": [car], "coordinator": None, "client": object()}}}})()
    out = []
    await switch_mod.async_setup_entry(hass, type("E", (), {"entry_id": "e1"})(), out.extend)

    ids = {s.unique_id for s in out}
    assert "ha_opencarwings_ac_VIN1" in ids
    assert "ha_opencarwings_cmd11_VIN1" not in ids
    assert "ha_opencarwings_cmd13_VIN1" not in ids
