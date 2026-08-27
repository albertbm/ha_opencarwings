"""Base entity shared by the OpenCARWINGS platforms."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN


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
