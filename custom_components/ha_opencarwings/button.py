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
    label: str
    # Phrase completing "Could not ..." in an error message.
    description: str
    icon: str
    diagnostic: bool = False


# Commands 1 and 2 have their own classes below, the paired start/stop ones are
# in switch.py, and 15 needs a config payload no plain button can supply.
#
# Lock and unlock are buttons rather than a lock entity: the TCU never reports
# door state.
COMMAND_BUTTONS: tuple[CommandButtonSpec, ...] = (
    CommandButtonSpec(CMD_DOOR_LOCK, "Lock", "lock the doors", "mdi:car-door-lock"),
    CommandButtonSpec(CMD_DOOR_UNLOCK, "Unlock", "unlock the doors", "mdi:car-door-lock-open"),
    CommandButtonSpec(CMD_CHARGE_START_80, "Charge to 80%", "start charging to 80%", "mdi:battery-80"),
    CommandButtonSpec(CMD_HORN, "Horn", "sound the horn", "mdi:bugle"),
    CommandButtonSpec(CMD_LIGHTS, "Lights", "flash the lights", "mdi:car-light-high"),
    CommandButtonSpec(CMD_READ_CONFIG, "Read Configuration", "read the car configuration", "mdi:cog-sync", diagnostic=True),
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")

    # Create a single per-entry refresh button
    entities = [OpenCarWingsRefreshButton(entry.entry_id, coordinator=coordinator)]

    # Create per-car API refresh buttons for each car
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

    # Tests set hass on the entity for direct method calls
    for ent in entities:
        ent.hass = hass

    async_add_entities(entities)


class OpenCarWingsRefreshButton(ButtonEntity):
    """Button that triggers a coordinator refresh when pressed."""

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
        """Press the button to force an immediate coordinator refresh."""
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
    """Button that sends a 'Refresh data' command for a specific car."""

    def __init__(self, entry_id: str, car: dict) -> None:
        self._entry_id = entry_id
        self._car = car
        self._vin = car.get("vin")

    @property
    def name(self) -> str:
        # Friendly label: prefer car nickname, then model name, then VIN
        label = self._car.get("nickname") or self._car.get("model_name") or self._vin
        return f"Request data refresh for {label}"

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
    """Button that sends a 'Charge start' command for a specific car."""

    def __init__(self, entry_id: str, car: dict) -> None:
        self._entry_id = entry_id
        self._car = car
        self._vin = car.get("vin")

    @property
    def name(self) -> str:
        # Friendly label: prefer car nickname, then model name, then VIN
        label = self._car.get("nickname") or self._car.get("model_name") or self._vin
        return f"Charge start for {label}"

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
    """Button that sends one remote command from COMMAND_BUTTONS."""

    def __init__(self, entry_id: str, car: dict, spec: CommandButtonSpec, coordinator=None) -> None:
        self._entry_id = entry_id
        self._seed_car = car or {}
        self._coordinator = coordinator
        self._vin = car.get("vin")
        self._spec = spec
        self._attr_icon = spec.icon
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
    def name(self) -> str:
        car = self._get_car()
        prefix = car.get("nickname") or car.get("model_name") or "Car"
        return f"{prefix} {self._spec.label}"

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
