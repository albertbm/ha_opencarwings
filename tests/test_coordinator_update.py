import pytest

from conftest import make_car

from custom_components.ha_opencarwings import sensor as sensor_mod


class FakeCoordinator:
    def __init__(self, data):
        self.data = data
        self._listeners = []
        self.last_update_time = None

    def async_add_listener(self, listener):
        self._listeners.append(listener)

        def _remove():
            self._listeners.remove(listener)

        return _remove

    def notify(self):
        for l in list(self._listeners):
            l()


@pytest.mark.asyncio
async def test_entities_update_on_coordinator_change():
    car1 = make_car(vin="VIN1", ev_info={"soc": 70})
    coord = FakeCoordinator([car1])

    hass = type(
        "H",
        (),
        {"data": {"ha_opencarwings": {"e1": {"coordinator": coord}}}},
    )()

    added = []

    def add(entities):
        added.extend(entities)

    entry = type("E", (), {"entry_id": "e1"})()
    await sensor_mod.async_setup_entry(hass, entry, add)

    def _val(e):
        return getattr(e, "native_value", getattr(e, "state", None))

    soc = next(
        x for x in added if getattr(x, "unique_id", None) == "ha_opencarwings_soc_VIN1"
    )
    assert _val(soc) == 70

    car1_updated = make_car(vin="VIN1", ev_info={"soc": 80})
    coord.data = [car1_updated]
    coord.notify()

    assert _val(soc) == 80


@pytest.mark.asyncio
async def test_odometer_present_when_full_payload_available():
    """The odometer shows once the VIN detail read has supplied it."""
    car = make_car(vin="VIN123", odometer=167504, ev_info={"soc": 55})
    coord = FakeCoordinator([car])

    hass = type(
        "H",
        (),
        {"data": {"ha_opencarwings": {"e1": {"coordinator": coord}}}},
    )()

    added = []

    def add(entities):
        added.extend(entities)

    entry = type("E", (), {"entry_id": "e1"})()
    await sensor_mod.async_setup_entry(hass, entry, add)

    odo = next(
        x
        for x in added
        if getattr(x, "unique_id", None) == "ha_opencarwings_odometer_VIN123"
    )

    assert odo.native_value == 167504
    assert odo._attr_native_unit_of_measurement == "km"


@pytest.mark.asyncio
async def test_soc_display_is_rounded_to_one_decimal():
    car = make_car(vin="VIN1", ev_info={"soc_display": 81.8043166797615})
    coord = FakeCoordinator([car])

    hass = type(
        "H",
        (),
        {"data": {"ha_opencarwings": {"e1": {"coordinator": coord}}}},
    )()

    added = []

    def add(entities):
        added.extend(entities)

    entry = type("E", (), {"entry_id": "e1"})()
    await sensor_mod.async_setup_entry(hass, entry, add)

    soc_disp = next(
        x
        for x in added
        if getattr(x, "unique_id", None)
        == "ha_opencarwings_soc_display_VIN1"
    )

    assert soc_disp.native_value == 81.8
