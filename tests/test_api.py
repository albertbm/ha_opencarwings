import pytest
from opencarwings_client import Car, CarSerializerList

from custom_components.ha_opencarwings import api


def test_client_carries_the_token_and_user_agent():
    client = api.get_client(None, "https://carwings.example.com", "secret")

    assert client.configuration.host == "https://carwings.example.com"
    assert client.configuration.api_key["Personal API Key"] == "secret"
    assert client.configuration.api_key_prefix["Personal API Key"] == "Token"
    assert client.default_headers["User-Agent"] == "OpenCARWINGS-HomeAssistant/1.0"


def test_client_without_a_token_sends_no_credentials():
    client = api.get_client(None, "https://carwings.example.com", None)

    assert "Personal API Key" not in client.configuration.api_key


def test_client_falls_back_to_the_public_server():
    assert api.get_client(None).configuration.host == api.DEFAULT_API_BASE


def test_a_supplied_session_is_reused():
    session = object()
    client = api.get_client(None, None, "k", session)

    # Home Assistant owns the session, so the client must not build its own.
    assert client.rest_client.pool_manager is session
    assert api.client_session(client) is session


def test_client_session_is_none_when_there_is_nothing_to_share():
    assert api.client_session(object()) is None


class _CarsApi:
    """Stands in for the generated CarsApi."""

    def __init__(self, listed, details):
        self._listed = listed
        self._details = details
        self.read_vins = []

    async def api_car_list(self):
        return self._listed

    async def api_car_read(self, vin):
        self.read_vins.append(vin)
        detail = self._details.get(vin)
        if isinstance(detail, Exception):
            raise detail
        return detail


def _listed(vin):
    return CarSerializerList.from_dict({"vin": vin, "ev_info": {}, "location": {}})


def _detail(vin, **over):
    return Car.from_dict({
        "vin": vin, "owner": 1, "sms_config": {}, "tcu_configuration": {},
        "location": {}, "ev_info": {}, "send_to_car_location_all": [],
        "route_plans": [], "timer_commands": [],
        "command_type_display": "Refresh data", "command_result_display": "OK",
        **over,
    })


@pytest.fixture
def cars_api(monkeypatch):
    def _install(listed, details):
        stub = _CarsApi(listed, details)
        monkeypatch.setattr(api.opencarwings_client, "CarsApi", lambda client: stub)
        return stub
    return _install


@pytest.mark.asyncio
async def test_every_car_is_listed_and_enriched(cars_api):
    stub = cars_api(
        [_listed("VIN1"), _listed("VIN2")],
        {"VIN1": _detail("VIN1", odometer=100), "VIN2": _detail("VIN2", odometer=200)},
    )

    cars = await api.async_list_cars(object())

    assert [c.vin for c in cars] == ["VIN1", "VIN2"]
    assert sorted(stub.read_vins) == ["VIN1", "VIN2"]
    assert cars[0].car_detail.odometer == 100


@pytest.mark.asyncio
async def test_a_failed_detail_leaves_the_listed_car_alone(cars_api):
    cars_api(
        [_listed("VIN1"), _listed("VIN2")],
        {"VIN1": RuntimeError("boom"), "VIN2": _detail("VIN2", odometer=200)},
    )

    cars = await api.async_list_cars(object())

    # The car survives on its list data; only the detail is missing.
    assert cars[0].car_detail is None
    assert cars[0].get_latest_car() is cars[0].list_car
    assert cars[1].car_detail.odometer == 200


@pytest.mark.asyncio
async def test_an_empty_account_reads_no_details(cars_api):
    stub = cars_api([], {})

    assert await api.async_list_cars(object()) == []
    assert stub.read_vins == []
