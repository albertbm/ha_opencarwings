from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

try:
    from homeassistant.exceptions import ServiceValidationError
except ImportError:  # pragma: no cover - older stubs
    class ServiceValidationError(Exception):  # type: ignore
        """Fallback used when the real exception cannot be imported."""

try:
    from homeassistant.exceptions import ConfigEntryAuthFailed
except ImportError:  # pragma: no cover - older stubs
    class ConfigEntryAuthFailed(Exception):  # type: ignore
        """Fallback used when the real exception cannot be imported."""

try:
    from homeassistant.exceptions import ConfigEntryNotReady
except ImportError:  # pragma: no cover - older stubs
    class ConfigEntryNotReady(Exception):  # type: ignore
        """Fallback used when the real exception cannot be imported."""

try:
    from homeassistant.const import CONF_API_KEY
except ImportError:  # pragma: no cover - older stubs
    CONF_API_KEY = "api_key"

DOMAIN = "ha_opencarwings"

# Config entry keys shared by the config flow and the platforms.
CONF_COMMAND_PIN = "command_pin"
PLATFORMS = ["sensor", "binary_sensor", "switch", "number", "device_tracker", "button"]

DEFAULT_SCAN_INTERVAL_MIN = 15

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one OpenCARWINGS account."""
    from opencarwings_client import ApiException

    from .api import async_list_cars, client_session, get_client
    from .util import CarData

    hass.data.setdefault(DOMAIN, {})

    # Options win over what setup wrote.
    opts = getattr(entry, "options", {}) or {}
    base_url = opts.get("api_base_url", entry.data.get("api_base_url"))

    api_key = (entry.data.get(CONF_API_KEY) or "").strip()
    if not api_key:
        # Nothing to authenticate with: this entry predates the API key.
        raise ConfigEntryAuthFailed("No API key stored for this account")

    session = _shared_session(hass)
    client = await hass.async_add_executor_job(
        get_client, hass, base_url, api_key, session
    )

    hass.data[DOMAIN][entry.entry_id] = {"client": client}

    async def _async_update_data() -> list[CarData]:
        """Read every car on this account."""
        try:
            return await async_list_cars(client)
        except ApiException as err:
            if getattr(err, "status", None) in (401, 403):
                raise ConfigEntryAuthFailed(err)
            raise UpdateFailed(err)
        except Exception as err:  # pragma: no cover - network or unexpected
            raise UpdateFailed(err)

    scan_min = opts.get("scan_interval", entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL_MIN))
    try:
        # Entries written before the selector stored strings carry one.
        scan_min = int(scan_min)
    except (TypeError, ValueError):
        scan_min = DEFAULT_SCAN_INTERVAL_MIN

    coordinator_kwargs = dict(
        name=f"{DOMAIN}_{entry.entry_id}",
        update_method=_async_update_data,
        update_interval=timedelta(minutes=scan_min),
    )
    try:
        coordinator = DataUpdateCoordinator(
            hass, _LOGGER, config_entry=entry, **coordinator_kwargs
        )
    except TypeError:  # pragma: no cover - stubs without config_entry
        coordinator = DataUpdateCoordinator(hass, _LOGGER, **coordinator_kwargs)

    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    try:
        await coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][entry.entry_id]["cars"] = coordinator.data or []
    except ConfigEntryAuthFailed as err:
        _LOGGER.warning("API key rejected; requesting reauthentication")
        raise ConfigEntryAuthFailed(err)
    except Exception as err:
        # There is no cache on a first setup, so let Home Assistant retry.
        raise ConfigEntryNotReady(err) from err

    _start_live_updates(
        hass, entry, client_session(client), coordinator, base_url, api_key
    )

    # Options otherwise sit unused until a restart. Not on the test stubs.
    if hasattr(entry, "add_update_listener") and hasattr(entry, "async_on_unload"):
        entry.async_on_unload(entry.add_update_listener(_async_update_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Once per hass, not once per entry.
    if not hass.data[DOMAIN].get("_service_refresh_registered"):
        async def _handle_refresh(call):
            """Re-read the server for one account, or all of them."""
            entry_id = (call.data or {}).get("entry_id") if call else None
            if entry_id:
                data = hass.data.get(DOMAIN, {}).get(entry_id)
                if not data:
                    _LOGGER.warning("Refresh requested for unknown entry %s", entry_id)
                    return
                coord = data.get("coordinator")
                if coord:
                    await coord.async_request_refresh()
            else:
                for d in hass.data.get(DOMAIN, {}).values():
                    # hass.data also holds plain flags.
                    if not isinstance(d, dict):
                        continue
                    coord = d.get("coordinator")
                    if coord:
                        await coord.async_request_refresh()

        async def _handle_ac_on(call):
            """Turn the climate on at a temperature."""
            from .commands import CMD_AC_ON, async_send_command

            data = call.data or {}
            found_entry_id, vin = _resolve_car(hass, data.get("entry_id"), data.get("vin"))
            await async_send_command(
                hass,
                found_entry_id,
                vin,
                CMD_AC_ON,
                "turn the climate on",
                command_payload=_ac_payload(data.get("temp"), data.get("unit", "celsius")),
            )

        try:
            hass.services.async_register(DOMAIN, "refresh", _handle_refresh)
            hass.services.async_register(DOMAIN, "ac_on", _handle_ac_on)
            hass.data[DOMAIN]["_service_refresh_registered"] = True
        except Exception:
            _LOGGER.debug("Could not register services (services not available in hass stub)")

    _LOGGER.info("OpenCARWINGS setup complete for %s", entry.title)
    return True


def _shared_session(hass):
    """Home Assistant's aiohttp session, when there is one."""
    try:
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        return async_get_clientsession(hass)
    except Exception:  # pragma: no cover - test stubs
        return None


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Strip the old sign-in so Home Assistant asks for an API key instead."""
    if entry.version == 1:
        data = {
            k: v
            for k, v in entry.data.items()
            if k not in ("username", "password", "access_token", "refresh_token")
        }
        data.setdefault(CONF_API_KEY, "")
        hass.config_entries.async_update_entry(entry, data=data, version=2)
        _LOGGER.info("Migrated %s to API key auth; an API key is now required", entry.title)

    return True


def _start_live_updates(hass, entry, session, coordinator, base_url, api_key) -> None:
    """Follow the server's push socket. Polling stays on as the safety net."""
    if not hasattr(hass, "async_create_task"):  # pragma: no cover - test stubs
        return

    if session is None or not hasattr(session, "ws_connect"):
        _LOGGER.debug("No websocket-capable session; staying on polling only")
        return

    from .websocket import DEFAULT_API_BASE_FALLBACK, CarWingsSocket

    socket = CarWingsSocket(
        hass, session, base_url or DEFAULT_API_BASE_FALLBACK, api_key, coordinator
    )
    socket.start()
    hass.data[DOMAIN][entry.entry_id]["socket"] = socket


def _ac_payload(temp, unit) -> dict:
    """Build the climate payload. Send both keys or the server drops the setpoint."""
    try:
        temp = int(temp)
    except (TypeError, ValueError):
        raise ServiceValidationError("temp must be a whole number between 0 and 31")
    if not 0 <= temp <= 31:
        raise ServiceValidationError(f"temp must be between 0 and 31, got {temp}")

    unit = str(unit or "celsius").lower()
    if unit not in ("celsius", "fahrenheit"):
        raise ServiceValidationError(f"unit must be celsius or fahrenheit, got {unit}")

    return {"temp": temp, "unit": 0 if unit == "celsius" else 1}


def _resolve_car(hass: HomeAssistant, entry_id: str | None, vin: str | None):
    """Find the entry and VIN to command. With one car, neither is needed."""
    cars_by_entry = {}
    for eid, data in hass.data.get(DOMAIN, {}).items():
        if not isinstance(data, dict):
            continue
        if entry_id and eid != entry_id:
            continue
        # cars is the setup-time snapshot; the coordinator has the live list.
        coord = data.get("coordinator")
        cars = getattr(coord, "data", None) or data.get("cars") or []
        vins = [str(c.vin) for c in cars if c.vin]
        if vins:
            cars_by_entry[eid] = vins

    if not cars_by_entry:
        raise ServiceValidationError("No OpenCARWINGS car is set up")

    if vin:
        for eid, vins in cars_by_entry.items():
            if vin in vins:
                return eid, vin
        raise ServiceValidationError(f"No car with VIN {vin} is set up")

    everything = [(eid, v) for eid, vins in cars_by_entry.items() for v in vins]
    if len(everything) > 1:
        raise ServiceValidationError(
            "More than one car is set up, so the vin field is required"
        )
    return everything[0]


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    stored = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None) or {}
    socket = stored.get("socket")
    if socket:
        await socket.stop()

    # Drop the services with the last entry, not the first.
    domain_data = hass.data.get(DOMAIN, {})
    services = getattr(hass, "services", None)
    if services and not any(isinstance(v, dict) for v in domain_data.values()):
        for service in ("refresh", "ac_on"):
            services.async_remove(DOMAIN, service)
        domain_data.pop("_service_refresh_registered", None)

    return unload_ok


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so updated options take effect."""
    await hass.config_entries.async_reload(entry.entry_id)
