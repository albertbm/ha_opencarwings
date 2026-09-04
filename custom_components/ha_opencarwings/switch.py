"""Switch platform for the climate and the paired remote commands."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .commands import (
    CMD_AC_OFF,
    CMD_AC_ON,
    CMD_HORN_LIGHTS,
    CMD_REMOTE_START,
    CMD_REMOTE_STOP,
    CMD_STOP_HORN_LIGHTS,
    EVENT_COMMAND_FINISHED,
    async_send_command,
    car_supports,
)
from .util import CarData
from .entity import async_add_cars

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandSwitchSpec:
    """A pair of commands that turn one thing on and off."""

    on_command: int
    off_command: int
    key: str
    # Phrases completing "Could not ..." in an error message.
    on_description: str
    off_description: str
    icon: str


COMMAND_SWITCHES: tuple[CommandSwitchSpec, ...] = (
    CommandSwitchSpec(
        CMD_REMOTE_START, CMD_REMOTE_STOP, "remote_start",
        "remote start the car", "remote stop the car", "mdi:car-key",
    ),
    CommandSwitchSpec(
        CMD_HORN_LIGHTS, CMD_STOP_HORN_LIGHTS, "horn_lights",
        "sound the horn and flash the lights", "stop the horn and lights",
        "mdi:car-emergency",
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")

    def _build(car: dict) -> list:
        entities = [CarClimateSwitch(coordinator, entry.entry_id, car)]
        # Both halves, or the toggle only works one way.
        for spec in COMMAND_SWITCHES:
            if car_supports(car, spec.on_command) and car_supports(car, spec.off_command):
                entities.append(CarCommandSwitch(entry.entry_id, car, spec, coordinator))
        return entities

    async_add_cars(hass, entry, async_add_entities, _build)


class CarClimateSwitch(CoordinatorEntity, SwitchEntity):
    """The car climate, following the server's reported ac_status."""

    _attr_has_entity_name = True
    _attr_translation_key = "climate"
    _attr_icon = "mdi:air-conditioner"
    # The server reports ac_status, so the state is real.
    _attr_assumed_state = False

    def __init__(self, coordinator, entry_id: str, car: CarData) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._seed_car = car
        self._vin = car.vin
        # What we asked for, until the car reports it or the command finishes.
        self._pending: bool | None = None
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        bus = getattr(self.hass, "bus", None)
        if bus:
            self._unsub = bus.async_listen(EVENT_COMMAND_FINISHED, self._command_finished)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    def _get_car(self) -> CarData:
        data = getattr(self.coordinator, "data", None) if self.coordinator else None
        for car in data or []:
            if car.vin == self._vin:
                return car
        return self._seed_car or CarData(self._vin)

    def _get_car_dict(self) -> dict:
        return self._get_car().as_dict()

    def _get_ev_dict(self) -> dict:
        return self._get_car_dict().get("ev_info") or {}

    def _reported(self) -> bool | None:
        ev = self._get_ev_dict()
        status = ev.get("ac_status")
        return None if status is None else bool(status)

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_ac_{self._vin}"

    @property
    def device_info(self) -> dict[str, Any]:
        return self._get_car().car_model_data()

    @property
    def is_on(self) -> bool | None:
        if self._pending is not None:
            return self._pending
        return self._reported()

    def _handle_coordinator_update(self) -> None:
        if self._pending is not None and self._reported() == self._pending:
            self._pending = None
        super()._handle_coordinator_update()

    @callback
    def _command_finished(self, event) -> None:
        """Stop guessing once the command is done, whatever it reported."""
        data = getattr(event, "data", None) or {}
        if data.get("vin") != self._vin:
            return
        if data.get("command_type") not in (CMD_AC_ON, CMD_AC_OFF):
            return
        self._pending = None
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        from .number import requested_temperature

        temp = requested_temperature(self.hass, self._entry_id, self._vin)
        await async_send_command(
            self.hass, self._entry_id, self._vin, CMD_AC_ON, "turn the climate on",
            command_payload={"temp": temp, "unit": 0},
        )
        self._pending = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await async_send_command(
            self.hass, self._entry_id, self._vin, CMD_AC_OFF, "turn the climate off"
        )
        self._pending = False
        self.async_write_ha_state()


class CarCommandSwitch(SwitchEntity):
    """Toggle backed by a pair of remote commands.

    The API reports no state for these, so this is the last command sent.
    """

    _attr_assumed_state = True
    _attr_has_entity_name = True

    def __init__(self, entry_id: str, car: dict, spec: CommandSwitchSpec, coordinator=None) -> None:
        self._entry_id = entry_id
        self._seed_car = car
        self._coordinator = coordinator
        self._vin = car.vin
        self._spec = spec
        self._attr_icon = spec.icon
        self._attr_translation_key = spec.key
        self._is_on = False

    def _get_car(self) -> CarData:
        data = getattr(self._coordinator, "data", None) if self._coordinator else None
        for car in data or []:
            if car.vin == self._vin:
                return car
        return self._seed_car or CarData(self._vin)

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_cmd{self._spec.on_command}_{self._vin}"

    @property
    def device_info(self) -> dict[str, Any]:
        return self._get_car().car_model_data()

    @property
    def is_on(self) -> bool:
        return self._is_on

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
