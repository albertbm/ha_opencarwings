"""OpenCARWINGS API client.

Wraps opencarwings_client with Home Assistant's shared aiohttp session, so we
do not open a second connection pool.
"""
from __future__ import annotations

import asyncio
import logging

import opencarwings_client

from .aioclient import RESTClientObject

_LOGGER = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://opencarwings.viaaq.eu"


class AuthenticationError(Exception):
    pass


class RequestError(Exception):
    pass


def get_client(hass, base_url: str | None = None, api_token: str | None = None,
               session=None) -> opencarwings_client.ApiClient:
    """Build a client. Blocking, so call it from an executor."""
    configuration = opencarwings_client.Configuration(host=base_url or DEFAULT_API_BASE)

    if api_token:
        configuration.api_key_prefix["Personal API Key"] = "Token"
        configuration.api_key["Personal API Key"] = api_token

    client = opencarwings_client.ApiClient(configuration)
    client.rest_client = RESTClientObject(configuration, session=session)
    client.set_default_header("User-Agent", "OpenCARWINGS-HomeAssistant/1.0")
    return client


def client_session(client) -> object | None:
    """The aiohttp session behind a client, for the push socket."""
    return getattr(getattr(client, "rest_client", None), "pool_manager", None)


async def async_list_cars(client) -> list:
    """Every car on the account, each with its detail merged in.

    The list endpoint omits the odometer and TCU versions, so read each by VIN.
    A failed detail leaves the list entry as it is.
    """
    from .util import CarData

    cars_api = opencarwings_client.CarsApi(client)
    cars = [CarData(vin=c.vin, list_car=c) for c in await cars_api.api_car_list()]

    by_vin = {str(c.vin): c for c in cars if c.vin}
    if not by_vin:
        return cars

    details = await asyncio.gather(
        *(cars_api.api_car_read(vin) for vin in by_vin), return_exceptions=True
    )
    for detail in details:
        if isinstance(detail, Exception):
            _LOGGER.debug("Could not read car detail: %s", detail)
        elif getattr(detail, "vin", None):
            by_vin[str(detail.vin)].car_detail = detail

    return cars
