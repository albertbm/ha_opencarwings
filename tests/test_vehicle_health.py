import pytest

from conftest import make_car
from custom_components.ha_opencarwings import binary_sensor as bin_mod
from custom_components.ha_opencarwings import sensor as sensor_mod


HEALTH = {
    "tpms_light": True,
    "tpms_fl": 221,
    "tpms_fl_float": 220.632,
    "tpms_fr": 224,
    "tpms_fr_float": 224.079,
    "tpms_rl": 0,
    "tpms_rl_float": 0,
    "tpms_rr": 217,
    "tpms_rr_float": 217.184,
    "maintenance_alert": False,
    "dtc_short": [{"ecu_id": 2, "ecu_label": "HVAC", "code_label": "P0123-45"}],
    "dtc_long": [
        {"ecu_id": 3, "ecu_label": "EV/HEV", "code_label": "C1234-67"},
        {"ecu_id": 4, "ecu_label": None, "code_label": "B0001-02"},
    ],
    "dtc_timestamp": "2026-01-04T14:00:00Z",
    "last_updated": "2026-01-04T14:05:00Z",
}

CAR = make_car(vin="VIN1", tcu_type="ficosa2016", veh_health=HEALTH)


class FakeCoordinator:
    def __init__(self, cars):
        self.data = cars

    def async_add_listener(self, cb):
        return lambda: None


async def _setup(module, car=CAR):
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {
        "coordinator": FakeCoordinator([car])}}}})()
    entry = type("E", (), {"entry_id": "e1"})()
    added = []
    await module.async_setup_entry(hass, entry, added.extend)
    return {e.unique_id: e for e in added}


@pytest.mark.asyncio
async def test_tyre_pressures_are_reported_in_kpa():
    by_id = await _setup(sensor_mod)
    assert by_id["ha_opencarwings_tpms_fl_VIN1"].native_value == 221
    assert by_id["ha_opencarwings_tpms_fr_VIN1"].native_value == 224
    assert by_id["ha_opencarwings_tpms_rr_VIN1"].native_value == 217


@pytest.mark.asyncio
async def test_a_wheel_with_no_reading_is_unknown():
    # The server sends 0 for a wheel it has heard nothing from.
    by_id = await _setup(sensor_mod)
    assert by_id["ha_opencarwings_tpms_rl_VIN1"].native_value is None


@pytest.mark.asyncio
async def test_fault_codes_are_counted_and_listed():
    by_id = await _setup(sensor_mod)
    dtc = by_id["ha_opencarwings_dtc_VIN1"]
    assert dtc.native_value == 3
    attrs = dtc.extra_state_attributes
    assert attrs["short_codes"] == ["P0123-45 (HVAC)"]
    assert attrs["long_codes"] == ["C1234-67 (EV/HEV)", "B0001-02"]


@pytest.mark.asyncio
async def test_fault_codes_accept_a_dict_from_the_server():
    car = make_car(vin="VIN1", tcu_type="ficosa2016", veh_health={
        **HEALTH, "dtc_short": {"0": {"code_label": "P0100-11"}}, "dtc_long": None})
    by_id = await _setup(sensor_mod, car)
    dtc = by_id["ha_opencarwings_dtc_VIN1"]
    assert dtc.native_value == 1
    assert dtc.extra_state_attributes["short_codes"] == ["P0100-11"]


@pytest.mark.asyncio
async def test_health_warnings_come_from_the_report():
    by_id = await _setup(bin_mod)
    assert by_id["ha_opencarwings_tpms_light_VIN1"].is_on is True
    assert by_id["ha_opencarwings_maintenance_alert_VIN1"].is_on is False


@pytest.mark.asyncio
async def test_a_car_with_no_health_report_still_gets_the_entities():
    # The server's own page lists every field whatever the car is fitted with.
    car = make_car(vin="VIN1", tcu_type="continental2012")
    sensors = await _setup(sensor_mod, car)
    binaries = await _setup(bin_mod, car)
    assert sensors["ha_opencarwings_tpms_fl_VIN1"].native_value is None
    assert sensors["ha_opencarwings_dtc_VIN1"].native_value is None
    assert binaries["ha_opencarwings_tpms_light_VIN1"].is_on is None


@pytest.mark.asyncio
async def test_cabin_temp_is_reported_when_the_car_sent_one():
    warm = make_car(vin="VIN1", ev_info={"cabin_temp": 21.5})
    cold = make_car(vin="VIN1", ev_info={"cabin_temp": -12.0})
    assert (await _setup(sensor_mod, warm))["ha_opencarwings_cabin_temp_VIN1"].native_value == 21.5
    assert (await _setup(sensor_mod, cold))["ha_opencarwings_cabin_temp_VIN1"].native_value == -12.0


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, 0.0, 87.5, None])
async def test_cabin_temp_ignores_the_no_data_values(value):
    # The server leaves the field at 0 when the car sent nothing, and decodes
    # the TCU's 0xFF invalid marker to 87.5.
    car = make_car(vin="VIN1", ev_info={"cabin_temp": value})
    by_id = await _setup(sensor_mod, car)
    assert by_id["ha_opencarwings_cabin_temp_VIN1"].native_value is None


@pytest.mark.asyncio
async def test_tcu_type_is_exposed_as_a_diagnostic():
    by_id = await _setup(sensor_mod)
    assert by_id["ha_opencarwings_tcu_type_VIN1"].native_value == "ficosa2016"
