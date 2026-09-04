import os
import sys

# Repo root on sys.path so `custom_components` imports work.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# tests/stubs holds the minimal "homeassistant" stub, so it goes first.
STUBS = os.path.join(os.path.dirname(__file__), "stubs")
if STUBS not in sys.path:
    sys.path.insert(0, STUBS)


def make_car(**fields):
    """A CarData carrying just the fields a test cares about.

    The generated Car model needs more than any one test wants to spell out,
    so the rest is filled in here.
    """
    from opencarwings_client import Car

    from custom_components.ha_opencarwings.util import CarData

    data = {
        "owner": 1,
        "sms_config": {},
        "tcu_configuration": {},
        "location": {},
        "ev_info": {},
        "send_to_car_location_all": [],
        "route_plans": [],
        "timer_commands": [],
        "command_type_display": "Refresh data",
        "command_result_display": "OK",
        **fields,
    }
    # The server sends coordinates as strings, and the model insists on them.
    location = data.get("location")
    if isinstance(location, dict):
        data["location"] = {
            k: (str(v) if k in ("lat", "lon") and v is not None else v)
            for k, v in location.items()
        }
    return CarData(vin=data["vin"], car_detail=Car.from_dict(data))


async def run_executor(func, *args):
    """Stand in for hass.async_add_executor_job."""
    return func(*args)


def stub_client(monkeypatch, cars=()):
    """Keep setup off the network, handing back the cars a test asks for."""
    from custom_components.ha_opencarwings import api

    async def _list(client):
        return list(cars)

    monkeypatch.setattr(api, "get_client", lambda *a, **kw: object())
    monkeypatch.setattr(api, "async_list_cars", _list)


def stub_commands(monkeypatch):
    """Capture commands instead of sending them. Returns the list of requests."""
    import opencarwings_client

    sent = []

    class _CarsApi:
        def __init__(self, client):
            pass

        async def api_command_create(self, vin, request):
            sent.append((vin, request))
            return type("R", (), {"car": None})()

    monkeypatch.setattr(opencarwings_client, "CarsApi", _CarsApi)
    return sent
