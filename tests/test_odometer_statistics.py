import pytest

from custom_components.ha_opencarwings import sensor as sensor_mod


@pytest.mark.asyncio
async def test_odometer_is_recorded_as_a_total():
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"cars": [
        {"vin": "VIN1", "nickname": "DKL", "odometer": 102592}]}}}})()
    entry = type("E", (), {"entry_id": "e1"})()
    added = []
    await sensor_mod.async_setup_entry(hass, entry, added.extend)

    odo = next(x for x in added if x.unique_id == "ha_opencarwings_odometer_VIN1")
    assert odo.native_value == 102592
    assert odo.device_class == "distance"
    assert odo.state_class == "total_increasing"
    assert odo.native_unit_of_measurement == "km"

    soc_range = next(x for x in added if x.unique_id == "ha_opencarwings_range_acoff_VIN1")
    assert soc_range.device_class == "distance"
    assert soc_range.state_class == "measurement"
