"""Diagnostics for a config entry, with the credentials taken out."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import DOMAIN

# The entry holds the API key and the command PIN; the car holds the TCU logins.
ENTRY_REDACT = {"api_key", "api_token", "command_pin", "access_token", "refresh_token"}
CAR_REDACT = {
    "vin", "tcu_user", "tcu_pass", "hmac_key", "sms_config", "iccid", "tcu_serial",
    "tcu_configuration", "vehicle_code1", "vehicle_code2", "vehicle_code3",
    "vehicle_code4", "lat", "lon",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    cars = getattr(coordinator, "data", None) or data.get("cars") or []

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), ENTRY_REDACT),
            "options": async_redact_data(dict(entry.options or {}), ENTRY_REDACT),
        },
        "socket_connected": data.get("socket") is not None,
        "cars": [async_redact_data(car.as_dict(), CAR_REDACT) for car in cars],
    }
