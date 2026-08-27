"""Base entity shared by the OpenCARWINGS platforms."""
from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN


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
            vin = car.get("vin")
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
    """One car, identified by VIN.

    Seed data from setup is merged under the coordinator payload so fields the
    poll leaves out do not disappear.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: dict | None = None) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._vin = vin
        self._seed_car = seed_car or {}

    def _get_car(self) -> dict:
        if self.coordinator and getattr(self.coordinator, "data", None):
            for car in self.coordinator.data:
                if car.get("vin") == self._vin:
                    return {**self._seed_car, **(car or {})}
        return self._seed_car or {}

    @property
    def device_info(self) -> dict[str, Any]:
        car = self._get_car()
        return {
            "identifiers": {(DOMAIN, self._vin)},
            "name": car.get("nickname") or car.get("model_name") or "Car",
            "manufacturer": car.get("make") or "Nissan",
            "model": car.get("model_name") or "Leaf",
        }
