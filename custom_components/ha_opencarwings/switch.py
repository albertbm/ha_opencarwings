"""Switch platform to control car climate (A/C) as a simple switch."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import logging

from homeassistant.components.switch import SwitchEntity

from . import DOMAIN
from .commands import (
    CMD_AC_OFF,
    CMD_AC_ON,
    CMD_HORN_LIGHTS,
    CMD_REMOTE_START,
    CMD_REMOTE_STOP,
    CMD_STOP_HORN_LIGHTS,
    async_send_command,
    car_supports,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandSwitchSpec:
    """A pair of commands that turn one thing on and off."""

    on_command: int
    off_command: int
    label: str
    # Phrases completing "Could not ..." in an error message.
    on_description: str
    off_description: str
    icon: str


COMMAND_SWITCHES: tuple[CommandSwitchSpec, ...] = (
    CommandSwitchSpec(
        CMD_REMOTE_START, CMD_REMOTE_STOP, "Remote Start",
        "remote start the car", "remote stop the car", "mdi:car-key",
    ),
    CommandSwitchSpec(
        CMD_HORN_LIGHTS, CMD_STOP_HORN_LIGHTS, "Horn and Lights",
        "sound the horn and flash the lights", "stop the horn and lights",
        "mdi:car-emergency",
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    cars = getattr(coordinator, "data", None) or data.get("cars", [])

    entities = []
    for car in cars:
        if not car.get("vin"):
            continue
        entities.append(CarACSwitch(entry.entry_id, car))
        # Both halves, or the toggle only works one way.
        for spec in COMMAND_SWITCHES:
            if car_supports(car, spec.on_command) and car_supports(car, spec.off_command):
                entities.append(CarCommandSwitch(entry.entry_id, car, spec, coordinator))

    # Tests call entity methods directly; set hass here for testability
    for ent in entities:
        ent.hass = hass

    async_add_entities(entities)


class CarACSwitch(SwitchEntity):
    """Represents the car A/C as a switch."""

    _attr_icon = "mdi:air-conditioner"

    def __init__(self, entry_id: str, car: dict) -> None:
        self._entry_id = entry_id
        self._car = car
        self._vin = car.get("vin")
        # state: True = on, False = off (no real-time state unless refreshed)
        self._is_on = False

    @property
    def name(self) -> str:
        return f"{self._car.get('model_name') or 'Car'} A/C"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_ac_{self._vin}"

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._vin)},
            "name": self._car.get("model_name"),
            "manufacturer": self._car.get("make"),
            "model": self._car.get("model_name"),
        }

    async def async_turn_on(self, **kwargs) -> None:
        await async_send_command(
            self.hass, self._entry_id, self._vin, CMD_AC_ON, "turn the A/C on"
        )
        self._is_on = True

    async def async_turn_off(self, **kwargs) -> None:
        await async_send_command(
            self.hass, self._entry_id, self._vin, CMD_AC_OFF, "turn the A/C off"
        )
        self._is_on = False



class CarCommandSwitch(SwitchEntity):
    """Toggle backed by a pair of remote commands.

    The API reports no state for these, so this is the last command sent.
    """

    _attr_assumed_state = True

    def __init__(self, entry_id: str, car: dict, spec: CommandSwitchSpec, coordinator=None) -> None:
        self._entry_id = entry_id
        self._seed_car = car or {}
        self._coordinator = coordinator
        self._vin = car.get("vin")
        self._spec = spec
        self._attr_icon = spec.icon
        self._is_on = False

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
        return f"ha_opencarwings_cmd{self._spec.on_command}_{self._vin}"

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def device_info(self) -> dict[str, Any]:
        car = self._get_car()
        return {
            "identifiers": {(DOMAIN, self._vin)},
            "name": car.get("nickname") or car.get("model_name"),
            "manufacturer": car.get("make"),
            "model": car.get("model_name"),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await async_send_command(
            self.hass, self._entry_id, self._vin,
            self._spec.on_command, self._spec.on_description,
        )
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await async_send_command(
            self.hass, self._entry_id, self._vin,
            self._spec.off_command, self._spec.off_description,
        )
        self._is_on = False
        self.async_write_ha_state()
