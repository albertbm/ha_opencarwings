from __future__ import annotations

import logging
from datetime import timedelta
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

try:
    from homeassistant.exceptions import ConfigEntryAuthFailed
except ImportError:  # pragma: no cover - older stubs
    class ConfigEntryAuthFailed(Exception):  # type: ignore
        """Fallback used when the real exception cannot be imported."""

try:
    from homeassistant.const import CONF_API_KEY
except ImportError:  # pragma: no cover - older stubs
    CONF_API_KEY = "api_key"

from .api import OpenCarWingsAPI, AuthenticationError, RequestError

DOMAIN = "ha_opencarwings"

# Config entry keys shared by the config flow and the platforms.
CONF_COMMAND_PIN = "command_pin"
CONF_GPS_MAX_RADIUS_KM = "gps_max_radius_km"
DEFAULT_GPS_MAX_RADIUS_KM = 0
PLATFORMS = ["sensor", "switch", "device_tracker", "button"]

# default: 15 minutes
DEFAULT_SCAN_INTERVAL_MIN = 15

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the OpenCARWINGS integration from a config entry with a DataUpdateCoordinator."""
    hass.data.setdefault(DOMAIN, {})

    # Respect configured API base URL (options override initial data)
    opts = getattr(entry, "options", {}) or {}
    base_url = opts.get("api_base_url", entry.data.get("api_base_url"))
    client = OpenCarWingsAPI(hass, base_url=base_url) if base_url else OpenCarWingsAPI(hass)

    api_key = (entry.data.get(CONF_API_KEY) or "").strip()
    if not api_key:
        # Nothing to authenticate with: this entry predates the API key.
        raise ConfigEntryAuthFailed("No API key stored for this account")
    client.set_api_key(api_key)

    # Ensure base_url is accessible on the client instance (helps tests and some clients)
    if base_url:
        # set both common attribute names
        try:
            setattr(client, "base_url", base_url)
            setattr(client, "_base", base_url)
        except Exception:
            pass

    # Store client in hass.data under the entry id
    hass.data[DOMAIN][entry.entry_id] = {"client": client}

    async def _enrich_cars_with_details(cars: list) -> list:
        """Enrich lite car objects (from /api/car/) with detail fetched by VIN."""
        if not isinstance(cars, list) or not cars:
            return cars
        if not hasattr(client, "async_get_car_by_vin"):
            return cars

        vins: list[str] = []
        tasks = []
        for c in cars:
            if isinstance(c, dict) and c.get("vin"):
                vin = str(c["vin"])
                vins.append(vin)
                tasks.append(client.async_get_car_by_vin(vin))

        if not tasks:
            return cars

        details = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge by VIN: detail wins, list fills missing fields
        by_vin: dict[str, dict] = {}
        for c in cars:
            if isinstance(c, dict) and c.get("vin"):
                by_vin[str(c["vin"])] = c

        for d in details:
            if isinstance(d, Exception) or not isinstance(d, dict):
                continue
            vin = d.get("vin")
            if not vin:
                continue
            vin = str(vin)
            by_vin[vin] = {**by_vin.get(vin, {}), **d}

        # Preserve list order
        out: list[dict] = []
        for c in cars:
            if isinstance(c, dict) and c.get("vin"):
                out.append(by_vin.get(str(c["vin"]), c))
            elif isinstance(c, dict):
                out.append(c)

        return out

    async def _async_update_data():
        """Fetch data from API."""
        from datetime import datetime, timezone

        try:
            # Prefer dedicated helper if available
            if hasattr(client, "async_get_cars"):
                cars = await client.async_get_cars()

                # Try to enrich with detail endpoint (to get odometer, versions, etc.)
                try:
                    cars = await _enrich_cars_with_details(cars)
                except Exception as err:
                    _LOGGER.debug("Could not enrich car list with details: %s", err)

                # Track the last successful update time for CarLastRequestedSensor
                coordinator.last_update_time = datetime.now(timezone.utc)
                return cars

            # Fallback to raw request-based client (used in tests)
            if hasattr(client, "async_request"):
                resp = await client.async_request("GET", "/api/car/")
                result = await resp.json()

                try:
                    result = await _enrich_cars_with_details(result)
                except Exception as err:
                    _LOGGER.debug("Could not enrich car list with details: %s", err)

                coordinator.last_update_time = datetime.now(timezone.utc)
                return result

            raise RuntimeError("Client has no method to fetch cars")

        except AuthenticationError as err:
            # Home Assistant turns this into a reauth flow.
            raise ConfigEntryAuthFailed(err)
        except RequestError as err:
            raise UpdateFailed(err)
        except Exception as err:  # pragma: no cover - network or unexpected
            raise UpdateFailed(err)

    # Determine scan interval from options (or fallback to default)
    scan_min = opts.get("scan_interval", entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL_MIN))

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{entry.entry_id}",
        update_method=_async_update_data,
        update_interval=timedelta(minutes=scan_min),
    )

    # store coordinator
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    # Do initial refresh to populate data
    try:
        await coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][entry.entry_id]["cars"] = coordinator.data or []
    except (ConfigEntryAuthFailed, AuthenticationError) as err:
        _LOGGER.warning("API key rejected; requesting reauthentication")
        raise ConfigEntryAuthFailed(err)
    except Exception:
        # Log the error but continue setup so platforms can use cached data if available
        _LOGGER.exception("Error while initializing OpenCARWINGS coordinator during setup")
        hass.data[DOMAIN][entry.entry_id]["cars"] = hass.data[DOMAIN][entry.entry_id].get("cars", [])
        # Don't abort setup; proceed to forward platforms so entity platforms can be set up
        pass

    # Options otherwise sit unused until a restart. Not on the test stubs.
    if hasattr(entry, "add_update_listener") and hasattr(entry, "async_on_unload"):
        entry.async_on_unload(entry.add_update_listener(_async_update_options))

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register integration service to allow manual refresh via service call
    # Register only once per hass instance
    if not hass.data[DOMAIN].get("_service_refresh_registered"):
        async def _handle_refresh(call):
            """Handle service call to refresh OpenCARWINGS data."""
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
                # refresh all coordinators
                for d in hass.data.get(DOMAIN, {}).values():
                    # skip non-dict sentinel values stored in hass.data (like flags)
                    if not isinstance(d, dict):
                        continue
                    coord = d.get("coordinator")
                    if coord:
                        await coord.async_request_refresh()

        try:
            hass.services.async_register(DOMAIN, "refresh", _handle_refresh)
            hass.data[DOMAIN]["_service_refresh_registered"] = True
        except Exception:
            # If hass.services isn't available in tests/stubs, ignore
            _LOGGER.debug("Could not register refresh service (services not available in hass stub)")

    _LOGGER.info("OpenCARWINGS setup complete for %s", entry.title)
    return True


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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove stored data
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so updated options take effect."""
    await hass.config_entries.async_reload(entry.entry_id)
