import pytest

from conftest import make_car, run_executor, stub_client

import custom_components.ha_opencarwings as init_mod
from custom_components.ha_opencarwings import api, device_tracker as tracker_mod
from custom_components.ha_opencarwings import websocket as ws


def test_a_push_keeps_the_fields_it_does_not_mention():
    """to_dict drops read-only fields, which would break every later push."""
    car = make_car(vin="VIN1", supported_commands=[1, 2, 3],
                   ev_info={"id": 1, "soc": 50.0},
                   location={"id": 7, "lat": "1.0", "lon": "2.0"})

    assert ws.apply_message([car], {"type": "ev_info", "data": {"id": 1, "soc": 61.5}})

    latest = car.get_latest_car()
    assert latest.supported_commands == [1, 2, 3]
    assert latest.ev_info.soc == 61.5
    # The ids have to survive or nothing matches next time.
    assert latest.ev_info.id == 1
    assert latest.location.id == 7


def test_a_second_push_still_finds_its_object():
    car = make_car(vin="VIN1", ev_info={"id": 1, "soc": 50.0},
                   location={"id": 7, "lat": "1.0", "lon": "2.0"})

    ws.apply_message([car], {"type": "ev_info", "data": {"id": 1, "soc": 61.5}})

    assert ws.apply_message([car], {"type": "location", "data": {"id": 7, "lat": "9.9"}})
    assert car.get_latest_car().location.lat == "9.9"


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


@pytest.mark.asyncio
async def test_a_server_that_is_down_at_setup_asks_home_assistant_to_retry(monkeypatch):
    async def _boom(client):
        raise RuntimeError("server down")

    monkeypatch.setattr(api, "get_client", lambda *a, **kw: object())
    monkeypatch.setattr(api, "async_list_cars", _boom)

    class C:
        async def async_forward_entry_setups(self, *args, **kwargs):
            return None

    hass = type("H", (), {"data": {}, "config_entries": C()})()
    hass.async_add_executor_job = run_executor
    entry = type("E", (), {"entry_id": "e1", "data": {"api_key": "k"}, "title": "t"})()

    # There is no cached data on a first setup, so setup must not report success.
    with pytest.raises(init_mod.ConfigEntryNotReady):
        await init_mod.async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_the_services_go_away_with_the_last_entry(monkeypatch):
    removed = []

    class Services:
        def async_register(self, domain, service, handler):
            return None

        def async_remove(self, domain, service):
            removed.append(service)

    class C:
        async def async_forward_entry_setups(self, *args, **kwargs):
            return None

        async def async_unload_platforms(self, *args, **kwargs):
            return True

    stub_client(monkeypatch, [make_car(vin="VIN1")])
    hass = type("H", (), {"data": {}, "config_entries": C(), "services": Services()})()
    hass.async_add_executor_job = run_executor
    entry = type("E", (), {"entry_id": "e1", "data": {"api_key": "k"}, "title": "t"})()

    await init_mod.async_setup_entry(hass, entry)
    await init_mod.async_unload_entry(hass, entry)

    assert sorted(removed) == ["ac_on", "refresh"]


@pytest.mark.parametrize("stored,expected", [(30, 30), ("30", 30), ("nonsense", 15), (None, 15)])
@pytest.mark.asyncio
async def test_a_stored_scan_interval_string_does_not_break_setup(monkeypatch, stored, expected):
    """The selector stores strings, and older entries stored ints."""
    captured = {}

    class Coordinator:
        def __init__(self, hass, logger, name=None, update_method=None,
                     update_interval=None, config_entry=None):
            captured["interval"] = update_interval
            self.data = []

        async def async_config_entry_first_refresh(self):
            return None

    class C:
        async def async_forward_entry_setups(self, *args, **kwargs):
            return None

    stub_client(monkeypatch, [])
    monkeypatch.setattr(init_mod, "DataUpdateCoordinator", Coordinator)

    hass = type("H", (), {"data": {}, "config_entries": C()})()
    hass.async_add_executor_job = run_executor
    entry = type("E", (), {
        "entry_id": "e1", "title": "t",
        "data": {"api_key": "k", "scan_interval": stored},
    })()

    assert await init_mod.async_setup_entry(hass, entry)
    assert captured["interval"].total_seconds() == expected * 60


@pytest.mark.asyncio
async def test_diagnostics_leave_no_credentials_behind():
    from custom_components.ha_opencarwings import diagnostics

    car = make_car(vin="VIN1", tcu_user="user", tcu_pass="secret",
                   location={"lat": "50.0", "lon": "20.0"},
                   tcu_configuration={"apn_password": "apnsecret"})
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"cars": [car]}}}})()
    entry = type("E", (), {
        "entry_id": "e1",
        "data": {"api_key": "topsecret", "api_base_url": "https://x.example"},
        "options": {"command_pin": "1234"},
    })()

    out = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    dump = repr(out)
    for secret in ("topsecret", "1234", "secret", "apnsecret", "VIN1", "50.0"):
        assert secret not in dump, secret
    # The useful parts survive.
    assert out["entry"]["data"]["api_base_url"] == "https://x.example"
    assert len(out["cars"]) == 1
