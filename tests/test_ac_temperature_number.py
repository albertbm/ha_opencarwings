import pytest

from conftest import make_car

from custom_components.ha_opencarwings import number as number_mod
from custom_components.ha_opencarwings import switch as switch_mod
from custom_components.ha_opencarwings.commands import CMD_AC_ON


class FakeCoordinator:
    def __init__(self, data):
        self.data = data
        self.last_update_success = True

    def async_add_listener(self, *args, **kwargs):
        return lambda: None


CAR = make_car(vin="VIN1", nickname="DKL", ev_info={"id": 1, "ac_status": False})


def _hass():
    return type("H", (), {"data": {"ha_opencarwings": {"e1": {
        "coordinator": FakeCoordinator([CAR])}}}, "bus": None})()


async def _number(hass):
    entry = type("E", (), {"entry_id": "e1"})()
    added = []
    await number_mod.async_setup_entry(hass, entry, added.extend)
    return added[0]


@pytest.mark.asyncio
async def test_defaults_to_21():
    hass = _hass()
    ent = await _number(hass)
    assert ent.native_value == 21
    assert ent.unique_id == "ha_opencarwings_requested_temp_VIN1"
    assert number_mod.requested_temperature(hass, "e1", "VIN1") == 21


@pytest.mark.asyncio
async def test_setting_it_is_clamped_and_published(monkeypatch):
    hass = _hass()
    ent = await _number(hass)
    monkeypatch.setattr(ent, "async_write_ha_state", lambda: None)

    await ent.async_set_native_value(18.6)
    assert ent.native_value == 19
    assert number_mod.requested_temperature(hass, "e1", "VIN1") == 19

    await ent.async_set_native_value(99)
    assert ent.native_value == 31
    await ent.async_set_native_value(-4)
    assert ent.native_value == 0


@pytest.mark.asyncio
async def test_switch_sends_the_stored_setpoint(monkeypatch):
    hass = _hass()
    ent = await _number(hass)
    monkeypatch.setattr(ent, "async_write_ha_state", lambda: None)
    await ent.async_set_native_value(17)

    sw = switch_mod.CarClimateSwitch(FakeCoordinator([CAR]), "e1", CAR)
    sw.hass = hass
    monkeypatch.setattr(sw, "async_write_ha_state", lambda: None)

    sent = []

    async def fake_send(hass, entry_id, vin, cmd, desc, command_payload=None, **kw):
        sent.append((cmd, command_payload))

    monkeypatch.setattr(switch_mod, "async_send_command", fake_send)
    await sw.async_turn_on()
    assert sent == [(CMD_AC_ON, {"temp": 17, "unit": 0})]


@pytest.mark.asyncio
async def test_unset_entry_falls_back_to_the_default():
    hass = type("H", (), {"data": {"ha_opencarwings": {}}})()
    assert number_mod.requested_temperature(hass, "nope", "VIN1") == 21
