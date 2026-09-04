"""Binary sensor platform for the car's on/off states."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

try:
    from homeassistant.helpers.entity import EntityCategory
except Exception:  # pragma: no cover
    class EntityCategory:  # type: ignore
        DIAGNOSTIC = "diagnostic"

from . import DOMAIN
from .entity import OpenCarwingsCarEntity, async_add_cars
from .util import CarData


@dataclass(frozen=True)
class CarBinarySensorSpec:
    key: str
    device_class: Optional[str] = None
    icon: Optional[str] = None
    diagnostic: bool = False


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
    CarBinarySensorSpec("batt_heater_status", BinarySensorDeviceClass.RUNNING,
                        "mdi:radiator"),
    CarBinarySensorSpec("batt_heater_avail", icon="mdi:radiator-disabled",
                        diagnostic=True),
    CarBinarySensorSpec("obc_6kw_avail", icon="mdi:flash", diagnostic=True),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")

    def _build(car: dict) -> list[CarBinarySensor]:
        return [
            CarBinarySensor(coordinator, entry.entry_id, car.vin, spec, car)
            for spec in CAR_BINARY_SENSORS
        ]

    async_add_cars(hass, entry, async_add_entities, _build)


class CarBinarySensor(OpenCarwingsCarEntity, BinarySensorEntity):
    """One boolean from the car's ev_info."""

    def __init__(self, coordinator, entry_id: str, vin: str,
                 spec: CarBinarySensorSpec, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._spec = spec
        self._attr_unique_id = f"ha_opencarwings_{spec.key}_{vin}"
        self._attr_translation_key = spec.key
        if spec.device_class:
            self._attr_device_class = spec.device_class
        if spec.icon:
            self._attr_icon = spec.icon
        if spec.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        value = self._get_ev_dict().get(self._spec.key)
        return None if value is None else bool(value)
