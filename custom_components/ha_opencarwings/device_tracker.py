"""Device tracker for the car's last known position."""
from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity

from . import DOMAIN
from .entity import async_add_cars
from .util import CarData


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

    def _get_car(self) -> CarData:
        data = getattr(self._coordinator, "data", None) if self._coordinator else None
        for car in data or []:
            if car.vin == self._vin:
                return car
        return self._seed_car or CarData(self._vin)

    def _lat_lon(self) -> tuple[float | None, float | None]:
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
    def device_info(self) -> dict:
        return self._get_car().car_model_data()

    async def async_added_to_hass(self) -> None:
        parent = getattr(super(), "async_added_to_hass", None)
        if parent is not None:
            await parent()

        add_listener = getattr(self._coordinator, "async_add_listener", None)
        if add_listener is not None and hasattr(self, "async_on_remove"):
            self.async_on_remove(add_listener(self.async_write_ha_state))
