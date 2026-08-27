"""The temperature to ask for when the climate is switched on."""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.restore_state import RestoreEntity

from . import DOMAIN
from .commands import CMD_AC_ON, car_supports
from .entity import OpenCarwingsCarEntity, async_add_cars

# The car takes a whole number in this range, in whichever unit it is told.
MIN_TEMP = 0
MAX_TEMP = 31
DEFAULT_TEMP = 21

STORE_KEY = "requested_temp"


def requested_temperature(hass, entry_id: str, vin: str) -> int:
    """The temperature the climate should be started at."""
    store = getattr(hass, "data", None) or {}
    data = store.get(DOMAIN, {}).get(entry_id) or {}
    return (data.get(STORE_KEY) or {}).get(vin, DEFAULT_TEMP)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")

    def _build(car: dict) -> list:
        if not car_supports(car, CMD_AC_ON):
            return []
        return [CarRequestedTemperature(coordinator, entry.entry_id, car["vin"], car)]

    async_add_cars(hass, entry, async_add_entities, _build)


class CarRequestedTemperature(OpenCarwingsCarEntity, RestoreEntity, NumberEntity):
    """The temperature sent with the next climate on command.

    The server never reports the car's setpoint back, so this is what was asked
    for, not what the car has.
    """

    _attr_translation_key = "requested_temp"
    _attr_icon = "mdi:thermometer"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = MIN_TEMP
    _attr_native_max_value = MAX_TEMP
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: dict | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_requested_temp_{vin}"
        self._value = DEFAULT_TEMP

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last:
            try:
                restored = int(float(last.state))
            except (TypeError, ValueError):
                restored = None
            if restored is not None and MIN_TEMP <= restored <= MAX_TEMP:
                self._value = restored
        self._publish()

    @property
    def native_value(self) -> float:
        return self._value

    def _publish(self) -> None:
        store = self.hass.data.setdefault(DOMAIN, {}).setdefault(self._entry_id, {})
        store.setdefault(STORE_KEY, {})[self._vin] = self._value

    async def async_set_native_value(self, value: float) -> None:
        self._value = max(MIN_TEMP, min(MAX_TEMP, int(round(value))))
        self._publish()
        self.async_write_ha_state()
