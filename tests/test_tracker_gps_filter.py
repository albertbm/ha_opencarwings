import pytest

from custom_components.ha_opencarwings import device_tracker as dt_mod


def _hass(radius=None, home=(52.0, 21.0)):
    """Stub hass carrying a home position and, optionally, the radius option."""
    options = {} if radius is None else {"gps_max_radius_km": radius}
    entry = type("E", (), {"entry_id": "e1", "options": options, "data": {}})()
    config = type("C", (), {"latitude": home[0], "longitude": home[1]})()
    entries = type("CE", (), {"async_get_entry": staticmethod(lambda _: entry)})()
    return type("H", (), {"config": config, "config_entries": entries})()


def _tracker(lat, lon, hass):
    car = {"vin": "VIN1", "last_location": {"lat": lat, "lon": lon}}
    tracker = dt_mod.CarTracker("e1", car)
    tracker.hass = hass
    return tracker


def test_filter_is_off_until_a_radius_is_set():
    # A fix on the far side of the planet still comes through.
    tracker = _tracker(-40.0, 175.0, _hass())
    assert (tracker.latitude, tracker.longitude) == (-40.0, 175.0)
    assert tracker.extra_state_attributes["gps_filter_rejected"] is False


def test_fix_inside_the_radius_is_kept():
    tracker = _tracker(52.1, 21.1, _hass(radius=75))
    assert tracker.latitude == pytest.approx(52.1)
    assert tracker.longitude == pytest.approx(21.1)


def test_fix_outside_the_radius_is_dropped():
    hass = _hass(radius=75)
    tracker = _tracker(52.1, 21.1, hass)
    assert tracker.latitude == pytest.approx(52.1)

    # The car cannot have moved 1000 km since the previous reading.
    tracker._seed_car["last_location"] = {"lat": 61.0, "lon": 25.0}
    assert tracker.latitude == pytest.approx(52.1)
    assert tracker.longitude == pytest.approx(21.1)

    rejected = tracker.extra_state_attributes["gps_filter_last_rejected_fix"]
    assert rejected["latitude"] == 61.0
    assert rejected["distance_from_home_km"] > 75


def test_bad_fix_with_no_good_one_yet_leaves_the_tracker_unavailable():
    tracker = _tracker(61.0, 25.0, _hass(radius=75))
    assert tracker.latitude is None
    assert tracker.available is False


def test_null_island_is_always_rejected():
    tracker = _tracker(0.0, 0.0, _hass(radius=75))
    assert tracker.latitude is None
