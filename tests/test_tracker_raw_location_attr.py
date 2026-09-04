import pytest

from conftest import make_car

from custom_components.ha_opencarwings import device_tracker as tracker_mod


@pytest.mark.asyncio
async def test_raw_location_is_exposed_as_an_attribute():
    car = make_car(vin="VIN1", location={"lat": "50.0", "lon": "20.0"})
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"cars": [car]}}}})()

    trackers = []
    entry = type("E", (), {"entry_id": "e1"})()
    await tracker_mod.async_setup_entry(hass, entry, trackers.extend)

    attrs = trackers[0].extra_state_attributes
    assert attrs["location_raw"]["lat"] == "50.0"
    assert attrs["location_raw"]["lon"] == "20.0"


@pytest.mark.asyncio
async def test_raw_location_is_none_when_the_car_has_no_fix():
    car = make_car(vin="VIN3")
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"cars": [car]}}}})()

    trackers = []
    entry = type("E", (), {"entry_id": "e1"})()
    await tracker_mod.async_setup_entry(hass, entry, trackers.extend)

    attrs = trackers[0].extra_state_attributes
    assert attrs["location_raw"] is None
