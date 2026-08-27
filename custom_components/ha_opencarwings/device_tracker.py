from __future__ import annotations

import logging
from math import asin, cos, radians, sin, sqrt
from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity

try:
    from homeassistant.helpers.restore_state import RestoreEntity
except Exception:  # pragma: no cover - tests running without hass stubs
    class RestoreEntity:  # type: ignore
        """Fallback base class used when RestoreEntity cannot be imported in tests."""
        pass

from . import CONF_GPS_MAX_RADIUS_KM, DEFAULT_GPS_MAX_RADIUS_KM, DOMAIN
from .entity import async_add_cars

_LOGGER = logging.getLogger(__name__)

# A head unit on the wrong map region, or with stale map data, can put the car
# a long way from where it is while the TCU has it right. Fixes beyond the
# configured radius from Home are dropped and the last good one held. Zero, the
# default, accepts everything.


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r_lat1, r_lat2 = radians(lat1), radians(lat2)
    d_lat = r_lat2 - r_lat1
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(r_lat1) * cos(r_lat2) * sin(d_lon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(a))


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")

    if coordinator and getattr(coordinator, "data", None) is None:
        if hasattr(coordinator, "async_request_refresh"):
            try:
                await coordinator.async_request_refresh()
            except Exception:  # pragma: no cover - network
                pass

    def _build(car: dict) -> list:
        return [CarTracker(entry.entry_id, car, coordinator)]

    async_add_cars(hass, entry, async_add_entities, _build)


class CarTracker(TrackerEntity, RestoreEntity):
    """Where the car is, per the server's last location fix."""

    _attr_has_entity_name = True
    _attr_translation_key = "tracker"

    def __init__(self, entry_id: str, car: dict, coordinator=None) -> None:
        self._entry_id = entry_id
        # Only a fallback for fields the coordinator does not carry.
        self._seed_car = car or {}
        self._coordinator = coordinator
        self._vin = car.get("vin")
        self._last_good: tuple[float, float] | None = None
        self._last_reject: dict[str, Any] | None = None

    def _get_car(self) -> dict:
        """Merge seed data with the latest coordinator payload for this VIN."""
        data = getattr(self._coordinator, "data", None) if self._coordinator else None
        if data:
            for car in data:
                if isinstance(car, dict) and car.get("vin") == self._vin:
                    return {**self._seed_car, **car}
        return self._seed_car

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_tracker_{self._vin}"

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    async def async_added_to_hass(self) -> None:
        """Seed the filter with the last good position from before a restart."""
        parent = getattr(super(), "async_added_to_hass", None)
        if parent is not None:
            await parent()

        add_listener = getattr(self._coordinator, "async_add_listener", None)
        if add_listener is not None and hasattr(self, "async_on_remove"):
            self.async_on_remove(add_listener(self.async_write_ha_state))

        get_last_state = getattr(self, "async_get_last_state", None)
        if get_last_state is None or self._last_good is not None:
            return

        last = await get_last_state()
        if last is None:
            return

        lat = last.attributes.get("latitude")
        lon = last.attributes.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            self._last_good = (float(lat), float(lon))
            _LOGGER.debug("%s: restored last good position %s", self.name, self._last_good)

    def _max_radius_km(self) -> float:
        """Configured radius in km. Zero or less means do not filter."""
        entries = getattr(getattr(self, "hass", None), "config_entries", None)
        if entries is None:
            return 0.0
        entry = entries.async_get_entry(self._entry_id)
        if entry is None:
            return 0.0
        value = entry.options.get(
            CONF_GPS_MAX_RADIUS_KM,
            entry.data.get(CONF_GPS_MAX_RADIUS_KM, DEFAULT_GPS_MAX_RADIUS_KM),
        )
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _home(self) -> tuple[float, float] | None:
        """Home Assistant's configured home position, or None."""
        config = getattr(getattr(self, "hass", None), "config", None)
        lat = getattr(config, "latitude", None)
        lon = getattr(config, "longitude", None)
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return float(lat), float(lon)
        return None

    def _raw_lat_lon(self):
        car = self._get_car()
        loc = car.get("last_location") or car.get("location")
        if loc is None and isinstance(car.get("ev_info"), dict):
            loc = car.get("ev_info", {}).get("last_location")

        if isinstance(loc, list) and len(loc) > 0:
            loc = loc[0]

        if isinstance(loc, dict):
            lat = loc.get("lat") or loc.get("latitude")
            lon = loc.get("lon") or loc.get("longitude")
            if lat is not None and lon is not None:
                # Accept commas as decimal separators ("53,0")
                try:
                    lat_f = float(str(lat).replace(",", "."))
                    lon_f = float(str(lon).replace(",", "."))
                    return lat_f, lon_f
                except Exception:
                    return None, None
        return None, None

    def _get_lat_lon(self):
        lat, lon = self._raw_lat_lon()
        if lat is None or lon is None:
            return self._last_good or (None, None)

        # Off the globe, or null island.
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0) or (
            abs(lat) < 1e-6 and abs(lon) < 1e-6
        ):
            self._reject(lat, lon, None)
            return self._last_good or (None, None)

        radius = self._max_radius_km()
        home = self._home()
        if radius <= 0 or home is None:
            # Nothing to filter against: no radius set, or no home position.
            self._last_good = (lat, lon)
            self._last_reject = None
            return self._last_good

        distance = _haversine_km(lat, lon, home[0], home[1])

        if distance <= radius:
            self._last_good = (lat, lon)
            self._last_reject = None
            return self._last_good

        self._reject(lat, lon, distance)
        return self._last_good or (None, None)

    def _car_label(self) -> str:
        car = self._get_car()
        return car.get("nickname") or car.get("model_name") or self._vin

    def _reject(self, lat: float, lon: float, distance: float | None) -> None:
        """Record a discarded fix; log it only the first time."""
        reject = {
            "latitude": lat,
            "longitude": lon,
            "distance_from_home_km": round(distance, 1) if distance is not None else None,
        }
        if reject != self._last_reject:
            _LOGGER.warning(
                "%s: discarding implausible GPS fix %.6f, %.6f (%s km from home, "
                "limit %s km); holding last known good position %s",
                self._car_label(),
                lat,
                lon,
                reject["distance_from_home_km"],
                self._max_radius_km(),
                self._last_good,
            )
        self._last_reject = reject

    @property
    def latitude(self) -> float | None:
        return self._get_lat_lon()[0]

    @property
    def longitude(self) -> float | None:
        return self._get_lat_lon()[1]

    @property
    def available(self) -> bool:
        lat, lon = self._get_lat_lon()
        return lat is not None and lon is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        car = self._get_car()
        raw_loc = None
        raw_src = None
        if isinstance(car.get("last_location"), dict):
            raw_loc = car.get("last_location")
            raw_src = "last_location"
        elif isinstance(car.get("last_location"), list) and len(car.get("last_location")) > 0:
            raw_loc = car.get("last_location")[0]
            raw_src = "last_location"
        elif isinstance(car.get("ev_info"), dict):
            raw_loc = car.get("ev_info", {}).get("last_location")
            if raw_loc is not None:
                raw_src = "ev_info.last_location"

        # Force the filter to run so the diagnostics below reflect this update.
        self._get_lat_lon()

        return {
            **car,
            "last_location_raw": raw_loc,
            "last_location_source": raw_src,
            "gps_filter_max_radius_km": self._max_radius_km(),
            "gps_filter_rejected": self._last_reject is not None,
            "gps_filter_last_rejected_fix": self._last_reject,
        }

    @property
    def device_info(self) -> dict[str, Any]:
        car = self._get_car()
        return {
            "identifiers": {(DOMAIN, self._vin)},
            "name": car.get("nickname") or car.get("model_name"),
            "manufacturer": car.get("make"),
            "model": car.get("model_name"),
        }
