import pytest

from conftest import make_car

from custom_components.ha_opencarwings import sensor as sensor_mod


@pytest.mark.asyncio
async def test_sensor_creates_car_entities():
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"cars": [make_car(vin="VIN1"), make_car(vin="VIN2")]}}}})()

    added = []

    def add(entities):
        added.extend(entities)

    entry = type("E", (), {"entry_id": "e1"})()
    await sensor_mod.async_setup_entry(hass, entry, add)

    # One list sensor, then every spec plus status, last updated, last
    # requested, VIN and fault codes per car. Booleans live on the
    # binary_sensor platform.
    per_car = len(sensor_mod.CAR_SENSORS) + 5
    assert len(added) == 1 + 2 * per_car

    unique_ids = [getattr(e, 'unique_id', None) for e in added]
    assert 'ha_opencarwings_range_acon_VIN1' in unique_ids
    assert 'ha_opencarwings_range_acoff_VIN2' in unique_ids

    car_entities = [e for e in added if getattr(e, "device_info", None) and e.device_info.get("identifiers")]
    vins = [list(e.device_info["identifiers"])[0][1] for e in car_entities]
    assert set(vins) == {"VIN1", "VIN2"}

    unique_ids = [e.unique_id for e in car_entities]

    expected_ids = {
        'ha_opencarwings_soc_VIN1', 'ha_opencarwings_soc_display_VIN1', 'ha_opencarwings_range_acon_VIN1', 'ha_opencarwings_range_acoff_VIN1', 'ha_opencarwings_charge_bars_VIN1', 'ha_opencarwings_odometer_VIN1', 'ha_opencarwings_full_chg_time_VIN1', 'ha_opencarwings_limit_chg_time_VIN1', 'ha_opencarwings_obc_6kw_VIN1', 'ha_opencarwings_last_updated_VIN1', 'ha_opencarwings_last_requested_VIN1', 'ha_opencarwings_vin_VIN1',
        'ha_opencarwings_soc_VIN2', 'ha_opencarwings_soc_display_VIN2', 'ha_opencarwings_range_acon_VIN2', 'ha_opencarwings_range_acoff_VIN2', 'ha_opencarwings_charge_bars_VIN2', 'ha_opencarwings_odometer_VIN2', 'ha_opencarwings_full_chg_time_VIN2', 'ha_opencarwings_limit_chg_time_VIN2', 'ha_opencarwings_obc_6kw_VIN2', 'ha_opencarwings_last_updated_VIN2', 'ha_opencarwings_last_requested_VIN2', 'ha_opencarwings_vin_VIN2',
    }
    assert expected_ids.issubset(set(unique_ids))
