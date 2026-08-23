"""Sends remote commands to `/api/command/{vin}/`.

Command numbers match COMMAND_TYPES in the upstream server's db/models.py.
"""
from __future__ import annotations

import logging
from typing import Any

try:
    from homeassistant.exceptions import HomeAssistantError
except Exception:  # pragma: no cover - tests running without hass stubs
    class HomeAssistantError(Exception):  # type: ignore
        """Fallback used when HomeAssistantError cannot be imported in tests."""

from . import CONF_COMMAND_PIN, DOMAIN

_LOGGER = logging.getLogger(__name__)

CMD_REFRESH = 1
CMD_CHARGE_START = 2
CMD_AC_ON = 3
CMD_AC_OFF = 4
CMD_READ_CONFIG = 5
CMD_CHARGE_START_80 = 6
CMD_DOOR_UNLOCK = 7
CMD_DOOR_LOCK = 8
CMD_HORN = 9
CMD_LIGHTS = 10
CMD_HORN_LIGHTS = 11
CMD_STOP_HORN_LIGHTS = 12
CMD_REMOTE_START = 13
CMD_REMOTE_STOP = 14


def car_supports(car: dict, command_type: int) -> bool:
    """Whether this car's TCU accepts a command.

    Older servers omit supported_commands; assume everything works.
    """
    supported = car.get("supported_commands")
    if not isinstance(supported, (list, tuple, set)) or not supported:
        return True
    return command_type in supported


def command_pin(hass, entry_id: str) -> str | None:
    """Read the command PIN from the config entry, options taking precedence."""
    entries = getattr(hass, "config_entries", None)
    if entries is None:
        return None
    entry = entries.async_get_entry(entry_id)
    if entry is None:
        return None
    pin = entry.options.get(CONF_COMMAND_PIN) or entry.data.get(CONF_COMMAND_PIN)
    return str(pin) if pin else None


async def _error_message(resp) -> str:
    """Pull the server's error text out of a failed command response."""
    try:
        body = await resp.json()
    except Exception:
        try:
            return (await resp.text())[:200]
        except Exception:
            return "unknown error"
    if isinstance(body, dict):
        return str(body.get("error") or body.get("detail") or body)
    return str(body)


async def async_send_command(
    hass,
    entry_id: str,
    vin: str,
    command_type: int,
    description: str,
) -> None:
    """Send one command, raising HomeAssistantError with the server's reason."""
    client = hass.data[DOMAIN][entry_id]["client"]

    payload: dict[str, Any] = {"vin": vin, "command_type": command_type}
    # Ignored by the server on commands that do not need it.
    pin = command_pin(hass, entry_id)
    if pin:
        payload["command_pin"] = pin

    try:
        resp = await client.async_request("POST", f"/api/command/{vin}/", json=payload)
    except Exception as err:  # pragma: no cover - network
        _LOGGER.exception("Failed to %s for %s", description, vin)
        raise HomeAssistantError(f"Could not {description}: {err}") from err

    # async_request returns the response untouched, so a rejected command
    # looks like a success unless we check.
    status = getattr(resp, "status", 200)
    if status >= 400:
        message = await _error_message(resp)
        if status == 403:
            message = (
                f"{message}. Set the command PIN in the OpenCARWINGS "
                "integration options (Settings > Devices & services > Configure)."
            )
        _LOGGER.error("%s failed for %s: HTTP %s %s", description, vin, status, message)
        raise HomeAssistantError(f"Could not {description}: {message}")

    # Pull fresh car data so the diagnostic timestamps reflect this request.
    try:
        coordinator = hass.data[DOMAIN][entry_id].get("coordinator")
        if coordinator:
            await coordinator.async_request_refresh()
    except Exception:  # pragma: no cover - coordinator failure
        _LOGGER.exception("Failed to refresh after %s for %s", description, vin)
