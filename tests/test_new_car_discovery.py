import pytest

from conftest import make_car

from custom_components.ha_opencarwings import binary_sensor as bs_mod
from custom_components.ha_opencarwings import button as button_mod
from custom_components.ha_opencarwings import device_tracker as tracker_mod
from custom_components.ha_opencarwings import number as number_mod
from custom_components.ha_opencarwings import sensor as sensor_mod
from custom_components.ha_opencarwings import switch as switch_mod

PLATFORMS = (sensor_mod, bs_mod, switch_mod, number_mod, button_mod, tracker_mod)


class FakeCoordinator:
    """Enough of DataUpdateCoordinator to push a new car list at the platforms."""

    def __init__(self, cars):
        self.data = cars
        self._listeners = []

    def async_add_listener(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def async_set_updated_data(self, cars):
        self.data = cars
        for listener in list(self._listeners):
            listener()


def _car(vin):
    return make_car(vin=vin, ev_info={"soc": 50}, location={"lat": "50.0", "lon": "20.0"})


class Entry:
    entry_id = "e1"

    def __init__(self):
        self.unsubscribes = []

    def async_on_unload(self, unsub):
        self.unsubscribes.append(unsub)


def _per_car(entities, vin):
    return [e for e in entities if (getattr(e, "unique_id", "") or "").endswith(vin)]


def _vins(entities):
    out = set()
    for e in entities:
        uid = getattr(e, "unique_id", "") or ""
        for vin in ("VIN1", "VIN2"):
            if uid.endswith(vin):
                out.add(vin)
    return out


@pytest.mark.asyncio
@pytest.mark.parametrize("module", PLATFORMS, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
async def test_car_added_after_setup_gets_entities(module):
    coordinator = FakeCoordinator([_car("VIN1")])
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": coordinator}}}})()
    entry = Entry()
    added = []

    await module.async_setup_entry(hass, entry, added.extend)
    assert _vins(added) == {"VIN1"}
    before = len(added)

    coordinator.async_set_updated_data([_car("VIN1"), _car("VIN2")])

    assert _vins(added) == {"VIN1", "VIN2"}
    new_car = _per_car(added, "VIN2")
    assert new_car
    assert len(_per_car(added, "VIN1")) == len(new_car)
    # The car already set up is not added a second time.
    assert len(added) == before + len(new_car)


@pytest.mark.asyncio
@pytest.mark.parametrize("module", PLATFORMS, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
async def test_repeat_updates_add_nothing(module):
    coordinator = FakeCoordinator([_car("VIN1")])
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": coordinator}}}})()
    added = []

    await module.async_setup_entry(hass, Entry(), added.extend)
    before = len(added)

    coordinator.async_set_updated_data([_car("VIN1")])
    coordinator.async_set_updated_data([_car("VIN1")])

    assert len(added) == before


@pytest.mark.asyncio
async def test_listener_is_released_on_unload():
    coordinator = FakeCoordinator([_car("VIN1")])
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": coordinator}}}})()
    entry = Entry()

    await sensor_mod.async_setup_entry(hass, entry, lambda entities: None)
    assert entry.unsubscribes

    for unsub in entry.unsubscribes:
        unsub()
    assert coordinator._listeners == []
