"""The requested temperature has to survive all the way to the wire.

Most cars ignore the setpoint, so this cannot be checked against hardware.
The server only encodes a real EVTemperaturePayload when both temp and unit
are present, and sends EVTemperatureDummy otherwise, without complaining.
"""
import pytest

from conftest import make_car

import opencarwings_client
from custom_components.ha_opencarwings import DOMAIN
from custom_components.ha_opencarwings import number as number_mod
from custom_components.ha_opencarwings import switch as switch_mod

CMD_AC_ON = 3
CMD_AC_OFF = 4


@pytest.fixture
def car_climate(monkeypatch):
    """A climate switch and its temperature number, wired to a stub API."""
    sent = []

    class _CarsApi:
        def __init__(self, _):
            pass

        async def api_command_create(self, vin, request):
            sent.append((vin, request))
            return type("R", (), {"car": None})()

    monkeypatch.setattr(opencarwings_client, "CarsApi", _CarsApi)

    car = make_car(vin="VIN1", nickname="DKL", supported_commands=[1, 2, 3, 4])
    hass = type("H", (), {"data": {DOMAIN: {"e1": {
        "client": object(), "coordinator": None, "cars": [car]}}}})()
    hass.config_entries = type("CE", (), {"async_get_entry": staticmethod(
        lambda _: type("E", (), {"options": {}, "data": {}})())})()
    entry = type("E", (), {"entry_id": "e1"})()

    async def _build():
        numbers = []
        await number_mod.async_setup_entry(hass, entry, numbers.extend)
        switches = []
        await switch_mod.async_setup_entry(hass, entry, switches.extend)
        climate = next(s for s in switches
                       if s.unique_id.startswith("ha_opencarwings_ac_"))
        numbers[0].hass = hass
        climate.hass = hass
        return numbers[0], climate, sent

    return _build


@pytest.mark.asyncio
@pytest.mark.parametrize("temp", [0, 16, 24, 31])
async def test_the_requested_temperature_reaches_the_client(car_climate, temp):
    number, climate, sent = await car_climate()

    await number.async_set_native_value(temp)
    await climate.async_turn_on()

    vin, request = sent[0]
    assert vin == "VIN1"
    # 0 is a real setpoint, so it must survive being falsy.
    assert request.to_dict() == {
        "command_type": CMD_AC_ON,
        "command_payload": {"temp": temp, "unit": 0},
    }


@pytest.mark.asyncio
async def test_turning_the_climate_off_sends_no_payload(car_climate):
    _, climate, sent = await car_climate()

    await climate.async_turn_off()

    # The server rejects a payload on commands that do not take one.
    wire = sent[0][1].to_dict()
    assert wire["command_type"] == CMD_AC_OFF
    assert "command_payload" not in wire


@pytest.mark.asyncio
async def test_the_setpoint_is_resent_on_every_climate_command(car_climate):
    """The server clears command_payload once it encodes the temperature."""
    number, climate, sent = await car_climate()

    await number.async_set_native_value(19)
    await climate.async_turn_on()
    await climate.async_turn_on()

    assert [r.command_payload for _, r in sent] == [
        {"temp": 19, "unit": 0},
        {"temp": 19, "unit": 0},
    ]
