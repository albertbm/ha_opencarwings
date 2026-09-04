"""Sends remote commands to `/api/command/{vin}/`.

Command numbers match COMMAND_TYPES in the upstream server's db/models.py.
"""
from __future__ import annotations

import asyncio
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

# command_result values from the server's COMMAND_RESULTS.
RESULT_WAITING = -1
RESULT_SUCCESS = 0
RESULT_ERROR = 1
RESULT_TIMEOUT = 2
RESULT_AWAIT_RESPONSE = 3
PENDING_RESULTS = (RESULT_WAITING, RESULT_AWAIT_RESPONSE)

RESULT_NAMES = {
    RESULT_SUCCESS: "success",
    RESULT_ERROR: "error",
    RESULT_TIMEOUT: "timeout",
}

# The server gives up on a command after five minutes.
POLL_INTERVAL = 10
POLL_TIMEOUT = 330

EVENT_COMMAND_FINISHED = f"{DOMAIN}_command_finished"


def car_supports(car, command_type: int) -> bool:
    """Whether this car's TCU accepts a command.

    Older servers omit supported_commands; assume everything works.
    """
    supported = getattr(car.get_latest_car(), "supported_commands", None)
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


def _error_message(err) -> str:
    """Pull the server's error text out of a failed command."""
    import json

    body = getattr(err, "body", None)
    if not body:
        return getattr(err, "reason", None) or "unknown error"
    try:
        parsed = json.loads(body)
    except Exception:
        return str(body)[:200]
    if isinstance(parsed, dict):
        return str(parsed.get("error") or parsed.get("detail") or parsed)
    return str(parsed)


def _apply_car(hass, entry_id: str, vin: str, car) -> None:
    """Push a freshly returned car into the coordinator."""
    if car is None:
        return
    coordinator = hass.data.get(DOMAIN, {}).get(entry_id, {}).get("coordinator")
    data = getattr(coordinator, "data", None)
    if not data:
        return
    for entry in data:
        if entry.vin == vin:
            entry.car_detail = car
            break
    else:
        return
    setter = getattr(coordinator, "async_set_updated_data", None)
    if setter:
        setter(data)


async def async_send_command(
    hass,
    entry_id: str,
    vin: str,
    command_type: int,
    description: str,
    command_payload: dict[str, Any] | None = None,
) -> None:
    """Send one command, raising HomeAssistantError with the server's reason."""
    import opencarwings_client
    from opencarwings_client import ApiCommandCreateRequest, ApiException

    client = hass.data[DOMAIN][entry_id]["client"]
    request = ApiCommandCreateRequest(
        command_type=command_type,
        # Only climate on and config accept a payload; others 400 with one.
        command_payload=command_payload,
        # Ignored by the server on commands that do not need it.
        command_pin=command_pin(hass, entry_id),
    )

    try:
        response = await opencarwings_client.CarsApi(client).api_command_create(vin, request)
    except ApiException as err:
        message = _error_message(err)
        if err.status == 403:
            message = (
                f"{message}. Set the command PIN in the OpenCARWINGS "
                "integration options (Settings > Devices & services > Configure)."
            )
        _LOGGER.error("%s failed for %s: HTTP %s %s", description, vin, err.status, message)
        raise HomeAssistantError(f"Could not {description}: {message}") from err
    except Exception as err:  # pragma: no cover - network
        _LOGGER.exception("Failed to %s for %s", description, vin)
        raise HomeAssistantError(f"Could not {description}: {err}") from err

    # The response carries the car as the server now has it.
    _apply_car(hass, entry_id, vin, getattr(response, "car", None))

    # Pull fresh car data so the diagnostic timestamps reflect this request.
    try:
        coordinator = hass.data[DOMAIN][entry_id].get("coordinator")
        if coordinator:
            await coordinator.async_request_refresh()
    except Exception:  # pragma: no cover - coordinator failure
        _LOGGER.exception("Failed to refresh after %s for %s", description, vin)

    _start_result_watch(hass, entry_id, vin, command_type, description)


def _start_result_watch(hass, entry_id: str, vin: str, command_type: int, description: str) -> None:
    """Follow the command until the car answers, without blocking the caller."""
    # A plain task would hold up startup and shutdown for the whole poll.
    create_task = getattr(hass, "async_create_background_task", None) or getattr(
        hass, "async_create_task", None
    )
    if create_task is None:  # pragma: no cover - minimal test stubs
        return

    watching = hass.data[DOMAIN].setdefault("_watching", set())
    key = (entry_id, vin)
    if key in watching:
        return
    watching.add(key)

    create_task(
        _async_watch_result(hass, entry_id, vin, command_type, description, key),
        f"{DOMAIN} await {description} {vin}",
    )


async def _async_watch_result(
    hass, entry_id: str, vin: str, command_type: int, description: str, key
) -> None:
    """Poll one car until its command resolves, then refresh the entities."""
    data = hass.data.get(DOMAIN, {}).get(entry_id) or {}
    client = data.get("client")
    coordinator = data.get("coordinator")
    watching = hass.data.get(DOMAIN, {}).get("_watching") or set()

    import opencarwings_client

    result = None
    waited = 0
    attempts = max(1, int(POLL_TIMEOUT // POLL_INTERVAL)) if POLL_INTERVAL else 1
    try:
        for _ in range(attempts):
            await asyncio.sleep(POLL_INTERVAL)
            waited += POLL_INTERVAL

            # Stop chasing a car whose entry has been unloaded.
            if entry_id not in hass.data.get(DOMAIN, {}):
                return
            try:
                car = await opencarwings_client.CarsApi(client).api_car_read(vin)
            except Exception as err:
                _LOGGER.debug("Could not read %s while awaiting %s: %s", vin, description, err)
                continue

            if car is None:
                continue
            _apply_car(hass, entry_id, vin, car)
            result = car.command_result
            if car.command_requested and result in PENDING_RESULTS:
                continue
            break
        else:
            result = RESULT_TIMEOUT

        if result == RESULT_SUCCESS:
            _LOGGER.info("Command to %s for %s succeeded after %ss", description, vin, waited)
        else:
            _LOGGER.warning(
                "Command to %s for %s ended as %s after %ss",
                description, vin, RESULT_NAMES.get(result, result), waited,
            )

        if coordinator:
            await coordinator.async_request_refresh()

        bus = getattr(hass, "bus", None)
        if bus:
            bus.async_fire(
                EVENT_COMMAND_FINISHED,
                {
                    "entry_id": entry_id,
                    "vin": vin,
                    "command_type": command_type,
                    "result": RESULT_NAMES.get(result, "unknown"),
                    "seconds": waited,
                },
            )
    finally:
        watching.discard(key)
