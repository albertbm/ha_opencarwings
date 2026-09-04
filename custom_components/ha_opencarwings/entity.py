"""Base entity shared by the OpenCARWINGS platforms."""
from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .util import CarData


@callback
def async_add_cars(hass, entry, async_add_entities, build) -> None:
    """Add entities per car, now and for cars that turn up later.

    A car added to the account arrives on the next poll or websocket push, so
    without this it would take a restart to see it.
    """
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    seen: set[str] = set()

    @callback
    def _add_missing() -> None:
        cars = getattr(coordinator, "data", None) or data.get("cars", [])
        entities = []
        for car in cars:
            vin = car.vin
            if not vin or vin in seen:
                continue
            seen.add(vin)
            entities.extend(build(car))
        if not entities:
            return
        # Tests call entity methods directly, so set hass here.
        for ent in entities:
            ent.hass = hass
        async_add_entities(entities)

    _add_missing()

    add_listener = getattr(coordinator, "async_add_listener", None)
    if add_listener is None:
        return
    unsub = add_listener(_add_missing)
    on_unload = getattr(entry, "async_on_unload", None)
    if on_unload:
        on_unload(unsub)


class OpenCarwingsCarEntity(CoordinatorEntity):
    """One car, identified by VIN."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._vin = vin
        self._seed_car = seed_car

    def _get_car(self) -> CarData:
        if self.coordinator and getattr(self.coordinator, "data", None):
            for c in self.coordinator.data:
                if c.vin == self._vin:
                    return c
        return self._seed_car or CarData(self._vin)

    def _get_car_dict(self) -> dict:
        return self._get_car().as_dict()

    def _get_ev_dict(self) -> dict:
        return self._get_car_dict().get("ev_info") or {}

    @property
    def device_info(self) -> dict[str, Any]:
        return self._get_car().car_model_data()
