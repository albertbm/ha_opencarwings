import pytest

from conftest import make_car

from custom_components.ha_opencarwings import device_tracker as tracker_mod


@pytest.mark.asyncio
async def test_the_tracker_publishes_position_and_nothing_else():
    """Matching renault and tesla_fleet: a car tracker carries no attributes.

    The recorder keeps attributes, so anything here is written to disk on
    every change, and the car's own fields already have their own entities.
    """
    car = make_car(vin="VIN1", location={"lat": "50.0", "lon": "20.0"},
                   tcu_user="user", tcu_pass="secret",
                   tcu_configuration={"apn_password": "apnsecret"})
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"cars": [car]}}}})()
    entry = type("E", (), {"entry_id": "e1"})()
    trackers = []
    await tracker_mod.async_setup_entry(hass, entry, trackers.extend)
    tracker = trackers[0]

    assert tracker.latitude == 50.0
    assert tracker.longitude == 20.0
    assert tracker.available is True
    # No custom attributes at all, so no credentials can leak through them.
    assert not (getattr(tracker, "extra_state_attributes", None) or {})
