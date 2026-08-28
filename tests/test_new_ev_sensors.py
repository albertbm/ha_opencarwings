import pytest

from custom_components.ha_opencarwings import binary_sensor as bs_mod
from custom_components.ha_opencarwings import sensor as sensor_mod


CAR = {
    "vin": "VIN1",
    "model_name": "M1",
    "odometer": 12345,
    "signal_level": 4,
    "carrier": "Telia",
    "ev_info": {
        "soh": 87,
        "wh_content": 18400.0,
        "gids": 230,
        "max_gids": 502,
        "cap_bars": 11,
        "counter": 7,
        "car_gear": 2,
        "batt_heater_status": True,
        "batt_heater_avail": True,
        "obc_6kw_avail": False,
    },
}


def _setup(module, car):
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"cars": [car]}}}})()
    added = []
    entry = type("E", (), {"entry_id": "e1"})()
    return hass, added, entry


async def _entities(module, car):
    hass, added, entry = _setup(module, car)
    await module.async_setup_entry(hass, entry, added.extend)
    return {e.unique_id: e for e in added}


@pytest.mark.asyncio
async def test_new_sensor_values():
    by_id = await _entities(sensor_mod, CAR)

    def val(key):
        return by_id[f"ha_opencarwings_{key}_VIN1"].native_value

    assert val("soh") == 87
    assert val("wh_content") == 18400.0
    assert val("gids") == 230
    assert val("max_gids") == 502
    assert val("cap_bars") == 11
    assert val("counter") == 7
    assert val("car_gear") == "reverse"
    assert val("signal_level") == 4
    assert val("carrier") == "Telia"


@pytest.mark.asyncio
async def test_gear_and_blank_carrier():
    car = {**CAR, "carrier": "  ", "ev_info": {**CAR["ev_info"], "car_gear": 0}}
    by_id = await _entities(sensor_mod, car)

    assert by_id["ha_opencarwings_car_gear_VIN1"].native_value == "park"
    assert by_id["ha_opencarwings_carrier_VIN1"].native_value is None


@pytest.mark.asyncio
async def test_defaults_read_as_unknown():
    """The server stores 0 for fields the car has never reported."""
    car = {**CAR, "odometer": -1, "ev_info": {**CAR["ev_info"], "soh": 0, "max_gids": 0}}
    by_id = await _entities(sensor_mod, car)

    assert by_id["ha_opencarwings_odometer_VIN1"].native_value is None
    assert by_id["ha_opencarwings_soh_VIN1"].native_value is None
    assert by_id["ha_opencarwings_max_gids_VIN1"].native_value is None


@pytest.mark.asyncio
async def test_new_binary_sensors():
    by_id = await _entities(bs_mod, CAR)

    assert by_id["ha_opencarwings_batt_heater_status_VIN1"].is_on is True
    assert by_id["ha_opencarwings_batt_heater_avail_VIN1"].is_on is True
    assert by_id["ha_opencarwings_obc_6kw_avail_VIN1"].is_on is False


@pytest.mark.asyncio
async def test_missing_fields_stay_none():
    car = {"vin": "VIN2", "model_name": "M2", "ev_info": {}}
    sensors = await _entities(sensor_mod, car)
    binaries = await _entities(bs_mod, car)

    for key in ("soh", "wh_content", "gids", "cap_bars", "car_gear", "carrier"):
        assert sensors[f"ha_opencarwings_{key}_VIN2"].native_value is None
    for key in ("batt_heater_status", "obc_6kw_avail"):
        assert binaries[f"ha_opencarwings_{key}_VIN2"].is_on is None


@pytest.mark.asyncio
async def test_kilometre_sensors_show_whole_numbers():
    by_id = await _entities(sensor_mod, CAR)

    for key in ("range_acon", "range_acoff", "odometer"):
        sensor = by_id[f"ha_opencarwings_{key}_VIN1"]
        assert sensor.suggested_display_precision == 0
