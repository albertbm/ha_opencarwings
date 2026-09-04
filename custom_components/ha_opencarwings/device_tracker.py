"""Device tracker for the car's last known position."""
from __future__ import annotations

import logging
from math import asin, cos, radians, sin, sqrt
from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity

from . import CONF_GPS_MAX_RADIUS_KM, DEFAULT_GPS_MAX_RADIUS_KM, DOMAIN
from .entity import async_add_cars
from .util import CarData

_LOGGER = logging.getLogger(__name__)

# A head unit on the wrong map region can put the car hundreds of km from where
# it is. Fixes beyond the configured radius from Home are dropped. Zero accepts
# everything.


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r_lat1, r_lat2 = radians(lat1), radians(lat2)
    d_lat = r_lat2 - r_lat1
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(r_lat1) * cos(r_lat2) * sin(d_lon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(a))


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")

    # Without a first fix there is nothing to place on the map.
    if coordinator is not None and getattr(coordinator, "data", None) is None:
        refresh = getattr(coordinator, "async_request_refresh", None)
        if refresh is not None:
            try:
                await refresh()
            except Exception:  # pragma: no cover - network
                pass

    def _build(car: CarData) -> list:
        if not car.vin:
            return []
        return [CarTracker(entry.entry_id, car, coordinator)]

    async_add_cars(hass, entry, async_add_entities, _build)


class CarTracker(TrackerEntity):
    """Where the car is, per the server's last location fix."""

    _attr_has_entity_name = True
    _attr_translation_key = "tracker"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        self._entry_id = entry_id
        self._seed_car = car
        self._coordinator = coordinator
        self._vin = car.vin
        self._last_good: tuple[float, float] | None = None
        self._last_reject: dict[str, Any] | None = None

    def _get_car(self) -> CarData:
        data = getattr(self._coordinator, "data", None) if self._coordinator else None
        for car in data or []:
            if car.vin == self._vin:
                return car
        return self._seed_car or CarData(self._vin)

    def _raw_lat_lon(self) -> tuple[float | None, float | None]:
        loc = self._get_car().as_dict().get("location")
        if not isinstance(loc, dict):
            return None, None

        lat, lon = loc.get("lat"), loc.get("lon")
        if lat is None or lon is None:
            return None, None
        try:
            # Some locales send a comma as the decimal separator.
            return (float(str(lat).replace(",", ".")),
                    float(str(lon).replace(",", ".")))
        except ValueError:
            return None, None

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

    def _lat_lon(self) -> tuple[float | None, float | None]:
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
                self._vin,
                lat,
                lon,
                reject["distance_from_home_km"],
                self._max_radius_km(),
                self._last_good,
            )
        self._last_reject = reject

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_tracker_{self._vin}"

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        return self._lat_lon()[0]

    @property
    def longitude(self) -> float | None:
        return self._lat_lon()[1]

    @property
    def available(self) -> bool:
        return self._lat_lon() != (None, None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        raw = self._get_car().as_dict().get("location")

        # Force the filter to run so the diagnostics below reflect this update.
        self._lat_lon()

        return {
            "location_raw": raw if isinstance(raw, dict) and raw else None,
            "gps_filter_max_radius_km": self._max_radius_km(),
            "gps_filter_rejected": self._last_reject is not None,
            "gps_filter_last_rejected_fix": self._last_reject,
        }

    @property
    def device_info(self) -> dict:
        return self._get_car().car_model_data()

    async def async_added_to_hass(self) -> None:
        parent = getattr(super(), "async_added_to_hass", None)
        if parent is not None:
            await parent()

        add_listener = getattr(self._coordinator, "async_add_listener", None)
        if add_listener is not None and hasattr(self, "async_on_remove"):
            self.async_on_remove(add_listener(self.async_write_ha_state))
