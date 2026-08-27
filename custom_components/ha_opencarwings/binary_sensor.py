"""Binary sensor platform for the car's on/off states."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from . import DOMAIN
from .entity import OpenCarwingsCarEntity


@dataclass(frozen=True)
class CarBinarySensorSpec:
    key: str
    device_class: Optional[str] = None
    icon: Optional[str] = None


CAR_BINARY_SENSORS: tuple[CarBinarySensorSpec, ...] = (
    CarBinarySensorSpec("plugged_in", BinarySensorDeviceClass.PLUG,
                        "mdi:ev-plug-type1"),
    CarBinarySensorSpec("charging", BinarySensorDeviceClass.BATTERY_CHARGING,
                        "mdi:battery-charging"),
    CarBinarySensorSpec("quick_charging",
                        BinarySensorDeviceClass.BATTERY_CHARGING, "mdi:ev-station"),
    CarBinarySensorSpec("charge_finish", icon="mdi:battery-check"),
    CarBinarySensorSpec("ac_status", icon="mdi:air-conditioner"),
    CarBinarySensorSpec("eco_mode", icon="mdi:leaf"),
    CarBinarySensorSpec("car_running", BinarySensorDeviceClass.RUNNING,
                        "mdi:car-electric"),
)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    cars = getattr(coordinator, "data", None) or data.get("cars", [])

    entities = [
        CarBinarySensor(coordinator, entry.entry_id, car["vin"], spec, car)
        for car in cars
        if car.get("vin")
        for spec in CAR_BINARY_SENSORS
    ]
    for ent in entities:
        ent.hass = hass

    async_add_entities(entities)


class CarBinarySensor(OpenCarwingsCarEntity, BinarySensorEntity):
    """One boolean field from the car's ev_info."""

    def __init__(self, coordinator, entry_id: str, vin: str,
                 spec: CarBinarySensorSpec, seed_car: dict | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._spec = spec
        self._attr_unique_id = f"ha_opencarwings_{spec.key}_{vin}"
        self._attr_translation_key = spec.key
        if spec.device_class:
            self._attr_device_class = spec.device_class
        if spec.icon:
            self._attr_icon = spec.icon

    @property
    def is_on(self) -> bool | None:
        ev = self._get_car().get("ev_info") or {}
        value = ev.get(self._spec.key)
        return None if value is None else bool(value)
