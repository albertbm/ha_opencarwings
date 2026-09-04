import pytest

from conftest import make_car

from custom_components.ha_opencarwings import device_tracker as tracker_mod


@pytest.mark.asyncio
async def test_tracker_reads_the_coordinates_the_server_sends():
    # The server sends lat and lon as strings, and some locales use a comma.
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"cars": [
        make_car(vin="VIN1", location={"lat": "50.0", "lon": "20.0"}),
        make_car(vin="VIN2", location={"lat": "53,0", "lon": "23,0"}),
    ]}}}})()

    trackers = []
    entry = type("E", (), {"entry_id": "e1"})()
    await tracker_mod.async_setup_entry(hass, entry, trackers.extend)

    by_vin = {t.unique_id.split("_")[-1]: t for t in trackers}

    assert round(by_vin["VIN1"].latitude, 3) == 50.0
    assert round(by_vin["VIN1"].longitude, 3) == 20.0
    assert round(by_vin["VIN2"].latitude, 3) == 53.0
    assert round(by_vin["VIN2"].longitude, 3) == 23.0


def test_tracker_leaves_the_state_to_home_assistant():
    """Overriding location_name is deprecated, and the API has no name to use."""
    from custom_components.ha_opencarwings import device_tracker as dt_mod

    assert "location_name" not in vars(dt_mod.CarTracker)
