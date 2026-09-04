import importlib

import pytest

from conftest import make_car, stub_commands

module = importlib.import_module("custom_components.ha_opencarwings")
from custom_components.ha_opencarwings import commands


def _hass(cars, entry_id="e1"):
    coord = type("C", (), {"data": cars})()
    return type("H", (), {"data": {"ha_opencarwings": {entry_id: {"coordinator": coord, "cars": cars}}}})()


def test_celsius_and_fahrenheit_map_to_the_unit_bit():
    assert module._ac_payload(21, "celsius") == {"temp": 21, "unit": 0}
    assert module._ac_payload(21, "fahrenheit") == {"temp": 21, "unit": 1}
    # The unit only picks the scale; temp passes through untouched.
    assert module._ac_payload("31", "Fahrenheit") == {"temp": 31, "unit": 1}
    assert module._ac_payload(0, None) == {"temp": 0, "unit": 0}


@pytest.mark.parametrize("temp", [-1, 32, 99, None, "warm"])
def test_temp_outside_the_five_bit_field_is_rejected(temp):
    with pytest.raises(module.ServiceValidationError):
        module._ac_payload(temp, "celsius")


def test_unknown_unit_is_rejected():
    with pytest.raises(module.ServiceValidationError):
        module._ac_payload(21, "kelvin")


def test_single_car_needs_no_vin():
    hass = _hass([make_car(vin="VIN1")])
    assert module._resolve_car(hass, None, None) == ("e1", "VIN1")


def test_two_cars_require_a_vin():
    hass = _hass([make_car(vin="VIN1"), make_car(vin="VIN2")])
    with pytest.raises(module.ServiceValidationError):
        module._resolve_car(hass, None, None)
    assert module._resolve_car(hass, None, "VIN2") == ("e1", "VIN2")


def test_unknown_vin_is_rejected():
    hass = _hass([make_car(vin="VIN1")])
    with pytest.raises(module.ServiceValidationError):
        module._resolve_car(hass, None, "NOPE")


@pytest.mark.asyncio
async def test_payload_rides_along_with_the_command(monkeypatch):
    sent = stub_commands(monkeypatch)

    class Entries:
        def async_get_entry(self, entry_id):
            return type("E", (), {"options": {}, "data": {}})()

    hass = type("H", (), {
        "data": {"ha_opencarwings": {"e1": {"client": object(), "coordinator": None}}},
        "config_entries": Entries(),
    })()

    await commands.async_send_command(
        hass, "e1", "VIN1", commands.CMD_AC_ON, "turn the A/C on",
        command_payload={"temp": 21, "unit": 0},
    )

    vin, request = sent[0]
    assert vin == "VIN1"
    assert request.command_payload == {"temp": 21, "unit": 0}
    assert request.command_type == commands.CMD_AC_ON


@pytest.mark.asyncio
async def test_commands_without_a_payload_send_none(monkeypatch):
    sent = stub_commands(monkeypatch)

    class Entries:
        def async_get_entry(self, entry_id):
            return type("E", (), {"options": {}, "data": {}})()

    hass = type("H", (), {
        "data": {"ha_opencarwings": {"e1": {"client": object(), "coordinator": None}}},
        "config_entries": Entries(),
    })()

    await commands.async_send_command(
        hass, "e1", "VIN1", commands.CMD_AC_OFF, "turn the A/C off"
    )

    # The server rejects a payload on every command except A/C on and config.
    assert sent[0][1].command_payload is None
