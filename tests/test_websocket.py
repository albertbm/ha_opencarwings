import pytest

from custom_components.ha_opencarwings import websocket as ws


def test_socket_url_follows_the_scheme():
    assert ws.socket_url("https://nissan.example.com") == "wss://nissan.example.com/ws/notif/"
    assert ws.socket_url("http://192.168.1.5:8000/") == "ws://192.168.1.5:8000/ws/notif/"
    assert ws.socket_url("nissan.example.com") == "wss://nissan.example.com/ws/notif/"


def _cars():
    return [{
        "vin": "VIN1",
        "nickname": "DKL",
        "ev_info": {"id": 1, "soc": 50.0, "ac_status": False},
        "location": {"id": 1, "lat": "64.1", "lon": "-21.8"},
    }]


def test_a_car_push_merges_onto_the_existing_car():
    out = ws.apply_message(_cars(), {"type": "car", "data": {"vin": "VIN1", "odometer": 102600}})
    assert out[0]["odometer"] == 102600
    # Fields the push does not mention survive.
    assert out[0]["nickname"] == "DKL"


def test_an_unknown_vin_is_added():
    out = ws.apply_message(_cars(), {"type": "car", "data": {"vin": "VIN2"}})
    assert [c["vin"] for c in out] == ["VIN1", "VIN2"]


def test_ev_info_is_matched_by_its_own_id():
    out = ws.apply_message(_cars(), {"type": "ev_info", "data": {"id": 1, "ac_status": True}})
    assert out[0]["ev_info"]["ac_status"] is True
    assert out[0]["ev_info"]["soc"] == 50.0


def test_location_is_matched_by_its_own_id():
    out = ws.apply_message(_cars(), {"type": "location", "data": {"id": 1, "lat": "66.3"}})
    assert out[0]["location"]["lat"] == "66.3"


def test_a_nested_object_for_an_unknown_car_changes_nothing():
    assert ws.apply_message(_cars(), {"type": "ev_info", "data": {"id": 99}}) is None


@pytest.mark.parametrize("message", [
    {"type": "send_to_car", "data": {"id": 1}},
    {"type": "car", "data": {"no_vin": True}},
    {"type": "car", "data": "not a dict"},
    {"nonsense": True},
    "not a message",
])
def test_messages_we_do_not_handle_are_ignored(message):
    assert ws.apply_message(_cars(), message) is None


class FakeCoordinator:
    def __init__(self, data):
        self.data = data
        self.pushed = None

    def async_set_updated_data(self, data):
        self.pushed = data


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, event, data):
        self.events.append((event, data))


def _socket(coordinator, bus):
    hass = type("H", (), {})()
    hass.bus = bus
    return ws.CarWingsSocket(hass, session=None, base_url="https://x.example", api_key="k", coordinator=coordinator)


def test_a_push_reaches_the_coordinator():
    coord = FakeCoordinator(_cars())
    sock = _socket(coord, FakeBus())

    sock._handle({"type": "ev_info", "data": {"id": 1, "soc": 61.5}})

    assert coord.pushed[0]["ev_info"]["soc"] == 61.5


def test_alerts_become_events_not_state():
    coord = FakeCoordinator(_cars())
    bus = FakeBus()
    sock = _socket(coord, bus)

    sock._handle({"type": "alert", "data": {"type": 97, "type_display": "A/C error"}})

    assert coord.pushed is None
    assert bus.events == [("ha_opencarwings_alert", {"type": 97, "type_display": "A/C error"})]
