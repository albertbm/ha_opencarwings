import pytest

from conftest import make_car

from custom_components.ha_opencarwings import binary_sensor as bin_mod


class FakeCoordinator:
    def __init__(self, data):
        self.data = data
        self.last_update_success = True

    def async_add_listener(self, *args, **kwargs):
        return lambda: None


CAR = make_car(vin="VIN1", nickname="DKL", ev_info={ "id": 1, "plugged_in": True, "charging": True, "quick_charging": False, "charge_finish": False, "ac_status": True, "eco_mode": False, "car_running": False, })


async def _setup(car=CAR):
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {
        "coordinator": FakeCoordinator([car])}}}})()
    entry = type("E", (), {"entry_id": "e1"})()
    added = []
    await bin_mod.async_setup_entry(hass, entry, added.extend)
    return {e.unique_id: e for e in added}


@pytest.mark.asyncio
async def test_one_entity_per_spec():
    by_id = await _setup()
    assert len(by_id) == len(bin_mod.CAR_BINARY_SENSORS)
    assert "ha_opencarwings_charging_VIN1" in by_id


@pytest.mark.asyncio
async def test_states_come_from_ev_info():
    by_id = await _setup()
    assert by_id["ha_opencarwings_plugged_in_VIN1"].is_on is True
    assert by_id["ha_opencarwings_charging_VIN1"].is_on is True
    assert by_id["ha_opencarwings_quick_charging_VIN1"].is_on is False
    assert by_id["ha_opencarwings_ac_status_VIN1"].is_on is True
    assert by_id["ha_opencarwings_car_running_VIN1"].is_on is False


@pytest.mark.asyncio
async def test_missing_field_reads_as_unknown():
    by_id = await _setup(make_car(vin="VIN1", nickname="DKL", ev_info={"id": 1}))
    assert by_id["ha_opencarwings_charging_VIN1"].is_on is None


@pytest.mark.asyncio
async def test_device_classes():
    by_id = await _setup()
    assert by_id["ha_opencarwings_plugged_in_VIN1"].device_class == "plug"
    assert by_id["ha_opencarwings_charging_VIN1"].device_class == "battery_charging"
    assert by_id["ha_opencarwings_car_running_VIN1"].device_class == "running"


@pytest.mark.asyncio
async def test_names_come_from_translations():
    by_id = await _setup()
    ent = by_id["ha_opencarwings_charging_VIN1"]
    assert ent._attr_has_entity_name is True
    assert ent._attr_translation_key == "charging"
