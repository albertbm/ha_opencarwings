"""Buttons for the manual refresh and the remote commands."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.button import ButtonEntity
from typing import Any

try:
    from homeassistant.helpers.entity import EntityCategory
except Exception:  # pragma: no cover - tests running without hass stubs
    class EntityCategory:  # type: ignore
        DIAGNOSTIC = "diagnostic"

from . import DOMAIN
from .commands import (
    CMD_CHARGE_START,
    CMD_CHARGE_START_80,
    CMD_DOOR_LOCK,
    CMD_DOOR_UNLOCK,
    CMD_HORN,
    CMD_LIGHTS,
    CMD_READ_CONFIG,
    CMD_REFRESH,
    async_send_command,
    car_supports,
)


@dataclass(frozen=True)
class CommandButtonSpec:
    """One remote command exposed as a button."""

    command_type: int
    key: str
    # Phrase completing "Could not ..." in an error message.
    description: str
    icon: str
    diagnostic: bool = False


# Commands 1 and 2 have their own classes below; the paired start/stop ones are
# in switch.py, and 15 needs a payload no plain button can supply. Lock and
# unlock stay buttons because the TCU never reports door state.
COMMAND_BUTTONS: tuple[CommandButtonSpec, ...] = (
    CommandButtonSpec(CMD_DOOR_LOCK, "lock", "lock the doors", "mdi:car-door-lock"),
    CommandButtonSpec(CMD_DOOR_UNLOCK, "unlock", "unlock the doors", "mdi:car-door-lock-open"),
    CommandButtonSpec(CMD_CHARGE_START_80, "charge_80", "start charging to 80%", "mdi:battery-80"),
    CommandButtonSpec(CMD_HORN, "horn", "sound the horn", "mdi:bugle"),
    CommandButtonSpec(CMD_LIGHTS, "lights", "flash the lights", "mdi:car-light-high"),
    CommandButtonSpec(CMD_READ_CONFIG, "read_config", "read the car configuration", "mdi:cog-sync", diagnostic=True),
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")

    entities = [OpenCarWingsRefreshButton(entry.entry_id, coordinator=coordinator)]

    cars = getattr(coordinator, "data", None) or data.get("cars", [])
    for car in cars:
        if not car.get("vin"):
            continue
        entities.append(CarRefreshButton(entry.entry_id, car))
        entities.append(CarChargeStartButton(entry.entry_id, car))
        # Only what this TCU accepts.
        for spec in COMMAND_BUTTONS:
            if car_supports(car, spec.command_type):
                entities.append(CarCommandButton(entry.entry_id, car, spec, coordinator))

    # Tests call entity methods directly, so set hass here.
    for ent in entities:
        ent.hass = hass

    async_add_entities(entities)


class OpenCarWingsRefreshButton(ButtonEntity):
    """Re-reads the server. Never contacts the car."""

    def __init__(self, entry_id: str, coordinator=None) -> None:
        self._entry_id = entry_id
        self._coordinator = coordinator

    @property
    def name(self) -> str:
        return "OpenCARWINGS Refresh"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_refresh_{self._entry_id}"

    async def async_press(self) -> None:
        if not self._coordinator:
            _LOGGER.warning("Refresh button pressed but coordinator is not available for %s", self._entry_id)
            return
        try:
            await self._coordinator.async_request_refresh()
        except Exception:  # pragma: no cover - network or unexpected
            _LOGGER.exception("Failed to refresh OpenCARWINGS data for %s", self._entry_id)
            raise

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"entry_id": self._entry_id}


class CarRefreshButton(ButtonEntity):
    """Asks the car to upload fresh data."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh"

    def __init__(self, entry_id: str, car: dict) -> None:
        self._entry_id = entry_id
        self._car = car
        self._vin = car.get("vin")

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_refresh_{self._vin}"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._vin)},
            "name": self._car.get("model_name"),
            "manufacturer": self._car.get("make"),
            "model": self._car.get("model_name"),
        }

    async def async_press(self) -> None:
        await async_send_command(
            self.hass, self._entry_id, self._vin, CMD_REFRESH, "refresh the car data"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"entry_id": self._entry_id, "vin": self._vin}



class CarChargeStartButton(ButtonEntity):
    """Tells the car to start charging."""

    _attr_has_entity_name = True
    _attr_translation_key = "charge_start"

    def __init__(self, entry_id: str, car: dict) -> None:
        self._entry_id = entry_id
        self._car = car
        self._vin = car.get("vin")

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_chargestart_{self._vin}"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._vin)},
            "name": self._car.get("model_name"),
            "manufacturer": self._car.get("make"),
            "model": self._car.get("model_name"),
        }

    async def async_press(self) -> None:
        await async_send_command(
            self.hass, self._entry_id, self._vin, CMD_CHARGE_START, "start charging"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"entry_id": self._entry_id, "vin": self._vin}

class CarCommandButton(ButtonEntity):
    """One remote command, pressed once."""

    _attr_has_entity_name = True

    def __init__(self, entry_id: str, car: dict, spec: CommandButtonSpec, coordinator=None) -> None:
        self._entry_id = entry_id
        self._seed_car = car or {}
        self._coordinator = coordinator
        self._vin = car.get("vin")
        self._spec = spec
        self._attr_icon = spec.icon
        self._attr_translation_key = spec.key
        if spec.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

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
        return f"ha_opencarwings_cmd{self._spec.command_type}_{self._vin}"

    @property
    def device_info(self) -> dict[str, Any]:
        car = self._get_car()
        return {
            "identifiers": {(DOMAIN, self._vin)},
            "name": car.get("nickname") or car.get("model_name"),
            "manufacturer": car.get("make"),
            "model": car.get("model_name"),
        }

    async def async_press(self) -> None:
        await async_send_command(
            self.hass,
            self._entry_id,
            self._vin,
            self._spec.command_type,
            self._spec.description,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "entry_id": self._entry_id,
            "vin": self._vin,
            "command_type": self._spec.command_type,
        }
