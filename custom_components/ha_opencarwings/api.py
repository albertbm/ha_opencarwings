"""Async client for the OpenCARWINGS API.

Every request carries an `Authorization: Token <key>` header. The key comes
from your account settings on the server, not from Home Assistant.
"""
from __future__ import annotations

import logging
from typing import Optional

try:
    from aiohttp import ClientResponse
except Exception:  # pragma: no cover - aiohttp not available in tests
    ClientResponse = object

from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://opencarwings.viaaq.eu"


class AuthenticationError(Exception):
    pass


class RequestError(Exception):
    pass


class OpenCarWingsAPI:
    def __init__(self, hass, base_url: str = DEFAULT_API_BASE, api_key: str | None = None) -> None:
        self.hass = hass
        # Import the helper dynamically so tests that monkeypatch
        # `homeassistant.helpers.aiohttp_client.async_get_clientsession`
        # will be respected.
        try:
            import importlib

            aiohttp_mod = importlib.import_module(
                "homeassistant.helpers.aiohttp_client"
            )
            self._session = aiohttp_mod.async_get_clientsession(hass)
        except Exception:  # pragma: no cover - fallback for tests
            self._session = None

        self._base = base_url.rstrip("/")
        self._api_key: Optional[str] = api_key

    def set_api_key(self, api_key: str | None) -> None:
        self._api_key = (api_key or "").strip() or None

    async def async_validate_api_key(self) -> list:
        """List the cars to see whether the key works. Raises AuthenticationError if not."""
        if not self._api_key:
            raise AuthenticationError("No API key set")
        return await self.async_get_cars()

    async def async_get_cars(self) -> list:
        """Retrieve a list of cars for the authenticated account.

        Returns a list of car objects (as dictionaries) on success.
        Raises RequestError or AuthenticationError on failures.
        """
        resp = await self.async_request("GET", "/api/car/")
        if resp.status in (401, 403):
            raise AuthenticationError("Not authorized to fetch cars")
        if resp.status != 200:
            text = await resp.text()
            _LOGGER.debug("Failed to fetch cars: %s %s", resp.status, text)
            raise RequestError(f"Failed fetching cars: {resp.status}")

        data = await resp.json()
        # Expecting an array of car objects
        return data

    async def async_request(self, method: str, path: str, **kwargs) -> ClientResponse:
        url = f"{self._base}{path if path.startswith('/') else '/' + path}"
        headers = kwargs.pop("headers", {}) or {}

        if self._api_key:
            headers["Authorization"] = f"Token {self._api_key}"

        try:
            resp = await self._session.request(method, url, headers=headers, **kwargs)
        except Exception as err:  # pragma: no cover - network error
            _LOGGER.exception("Request to OpenCARWINGS failed")
            raise RequestError(err)

        return resp

    async def async_get_car_by_vin(self, vin: str) -> dict:
        """Retrieve full car detail by VIN."""
        vin = (vin or "").strip()
        if not vin:
            raise RequestError("VIN missing")

        path = f"/api/car/{vin}/"

        resp = await self.async_request("GET", path)
        if resp.status in (401, 403):
            raise AuthenticationError("Not authorized to fetch car detail")
        if resp.status != 200:
            text = await resp.text()
            _LOGGER.debug("Failed to fetch car detail by VIN %s: %s %s", vin, resp.status, text)
            raise RequestError(f"Failed fetching car detail by VIN: {resp.status}")

        return await resp.json()
