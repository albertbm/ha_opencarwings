"""Sensor platform for the car's readings and diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION, PERCENTAGE, UnitOfEnergy, UnitOfLength
from homeassistant.helpers.update_coordinator import CoordinatorEntity

try:
    from homeassistant.helpers.entity import EntityCategory
except Exception:  # pragma: no cover
    class EntityCategory:  # type: ignore
        DIAGNOSTIC = "diagnostic"

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from . import DOMAIN
from .entity import OpenCarwingsCarEntity

_LOGGER = logging.getLogger(__name__)


def _parse_ts(value: str | None):
    if not value:
        return None
    try:
        # The server sends both `...:00Z` and `...:00.419903Z`.
        if value.endswith("Z"):
            try:
                return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            except ValueError:
                return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """Return a timezone-aware datetime; the timestamp device class needs one."""
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _relative_str(dt: datetime | None) -> str | None:
    """Render a datetime as "5 minutes ago" / "in 2 hours" style text."""
    dt = _ensure_aware(dt)
    if dt is None:
        return None

    delta = (datetime.now(timezone.utc) - dt).total_seconds()
    future = delta < 0
    delta = abs(delta)

    if delta < 45:
        return "just now"

    minute, hour, day, week = 60, 3600, 86400, 604800
    for limit, size, unit in (
        (90 * minute, minute, "minute"),
        (36 * hour, hour, "hour"),
        (14 * day, day, "day"),
        (10 * week, week, "week"),
    ):
        if delta < limit:
            count = round(delta / size)
            break
    else:
        count = round(delta / (30 * day))
        unit = "month"

    plural = "" if count == 1 else "s"
    return f"in {count} {unit}{plural}" if future else f"{count} {unit}{plural} ago"


def _format_dt(dt: datetime | None) -> str | None:
    if not dt:
        return None
    try:
        ts = dt.isoformat()
        if ts.endswith("+00:00"):
            ts = ts.replace("+00:00", "Z")
        return ts
    except Exception:
        return None


def _ev_getter(key: str, fallback: str | None = None) -> Callable[[dict], Any]:
    """Get value from car['ev_info'][key], falling back to car[fallback] or car[key]."""
    def _get(car: dict):
        ev = car.get("ev_info") or {}
        if isinstance(ev, dict) and key in ev:
            return ev.get(key)
        if fallback:
            return car.get(fallback)
        return car.get(key)
    return _get

def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None

# Zero and the top values of the field mean "no estimate"; the server UI
# draws them as "--:--".
_CHG_TIME_UNAVAILABLE = {0, 2047, 4095}


def _chg_minutes(v: Any) -> int | None:
    """Charge time in minutes, or None when the car has no estimate."""
    if v is None:
        return None
    try:
        minutes = int(v)
    except Exception:
        return None
    if minutes in _CHG_TIME_UNAVAILABLE or minutes < 1:
        return None
    return minutes


def _round_1(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return round(float(v), 1)
    except Exception:
        return None


# Gear values as the server stores them.
CAR_GEAR = {0: "park", 1: "drive", 2: "reverse"}


def _gear(v: Any) -> str | None:
    return CAR_GEAR.get(_to_int(v))


def _positive_int(v: Any) -> int | None:
    """0 and -1 are the server's defaults, not readings from the car."""
    n = _to_int(v)
    return n if n is not None and n > 0 else None


def _text(v: Any) -> str | None:
    v = (v or "").strip() if isinstance(v, str) else v
    return v or None


@dataclass(frozen=True)
class CarSensorSpec:
    key: str
    value: Callable[[dict], Any]
    transform: Optional[Callable[[Any], Any]] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    unit_of_measurement: Optional[str] = None
    suggested_unit: Optional[str] = None
    icon: Optional[str] = None
    options: Optional[tuple[str, ...]] = None
    diagnostic: bool = False


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None


CAR_SENSORS: list[CarSensorSpec] = [
    CarSensorSpec(
        "range_acon",
        _ev_getter("range_acon"),
        transform=_to_float,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_of_measurement=UnitOfLength.KILOMETERS,
        icon="mdi:map-marker-distance",
    ),
    CarSensorSpec(
        "range_acoff",
        _ev_getter("range_acoff"),
        transform=_to_float,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_of_measurement=UnitOfLength.KILOMETERS,
        icon="mdi:map-marker-distance",
    ),
    CarSensorSpec("soc", _ev_getter("soc"), transform=_round_1, device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT, unit_of_measurement=PERCENTAGE),
    CarSensorSpec("soc_display", _ev_getter("soc_display"), transform=_round_1, device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT, unit_of_measurement=PERCENTAGE),
    CarSensorSpec("charge_bars", _ev_getter("charge_bars"), icon="mdi:battery-charging-medium"),
    CarSensorSpec(
        "odometer",
        lambda car: car.get("odometer"),
        transform=_positive_int,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        unit_of_measurement=UnitOfLength.KILOMETERS,
        icon="mdi:counter",
    ),
    CarSensorSpec(
        "full_chg_time",
        _ev_getter("full_chg_time"),
        transform=_chg_minutes,
        device_class=SensorDeviceClass.DURATION,
        unit_of_measurement="min",
        icon="mdi:timer-sand",
    ),
    CarSensorSpec(
        "limit_chg_time",
        _ev_getter("limit_chg_time"),
        transform=_chg_minutes,
        device_class=SensorDeviceClass.DURATION,
        unit_of_measurement="min",
        icon="mdi:timer-sand",
    ),
    CarSensorSpec(
        "obc_6kw",
        _ev_getter("obc_6kw"),
        transform=_chg_minutes,
        device_class=SensorDeviceClass.DURATION,
        unit_of_measurement="min",
        icon="mdi:timer-sand",
    ),
    CarSensorSpec(
        "soh",
        _ev_getter("soh"),
        transform=_positive_int,
        state_class=SensorStateClass.MEASUREMENT,
        unit_of_measurement=PERCENTAGE,
        icon="mdi:battery-heart-variant",
    ),
    CarSensorSpec(
        "wh_content",
        _ev_getter("wh_content"),
        transform=_to_float,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:battery-charging",
    ),
    CarSensorSpec(
        "gids",
        _ev_getter("gids"),
        transform=_to_int,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-medium",
    ),
    CarSensorSpec(
        "cap_bars",
        _ev_getter("cap_bars"),
        transform=_to_int,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart-outline",
    ),
    CarSensorSpec(
        "car_gear",
        _ev_getter("car_gear"),
        transform=_gear,
        device_class=SensorDeviceClass.ENUM,
        options=tuple(CAR_GEAR.values()),
        icon="mdi:car-shift-pattern",
    ),
    CarSensorSpec(
        "signal_level",
        lambda car: car.get("signal_level"),
        transform=_to_int,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
        diagnostic=True,
    ),
    CarSensorSpec(
        "carrier",
        lambda car: car.get("carrier"),
        transform=_text,
        icon="mdi:sim",
        diagnostic=True,
    ),
    CarSensorSpec(
        "max_gids",
        _ev_getter("max_gids"),
        transform=_positive_int,
        icon="mdi:battery-high",
        diagnostic=True,
    ),
    CarSensorSpec(
        "counter",
        _ev_getter("counter"),
        transform=_to_int,
        icon="mdi:counter",
        diagnostic=True,
    ),
]


class CarValueSensor(OpenCarwingsCarEntity, SensorEntity):
    """One value from CAR_SENSORS."""

    def __init__(self, coordinator, entry_id: str, vin: str, spec: CarSensorSpec, seed_car: dict | None = None) -> None:
        OpenCarwingsCarEntity.__init__(self, coordinator, entry_id, vin, seed_car)
        self._spec = spec
        self._attr_unique_id = f"ha_opencarwings_{spec.key}_{vin}"
        self._attr_translation_key = spec.key
        if spec.device_class:
            self._attr_device_class = spec.device_class
        if spec.state_class:
            self._attr_state_class = spec.state_class
        if spec.icon:
            self._attr_icon = spec.icon
        if spec.unit_of_measurement:
            self._attr_native_unit_of_measurement = spec.unit_of_measurement
        if spec.suggested_unit:
            self._attr_suggested_unit_of_measurement = spec.suggested_unit
        if spec.options:
            self._attr_options = list(spec.options)
        if spec.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        car = self._get_car()
        val = self._spec.value(car)

        if self._spec.transform:
            return self._spec.transform(val)
        return val


class CarStatusSensor(OpenCarwingsCarEntity, SensorEntity):
    """High-level status string for the car (charging, running, ac_on, idle)."""

    _attr_icon = "mdi:car-info"

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: dict | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_status_{vin}"
        self._attr_translation_key = "status"

    @property
    def native_value(self) -> str:
        car = self._get_car()
        ev = car.get("ev_info", {}) or {}
        if ev.get("charging"):
            return "charging"
        if ev.get("car_running"):
            return "running"
        if ev.get("ac_status"):
            return "ac_on"
        return "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        car = self._get_car()
        ev = car.get("ev_info", {}) or {}
        return {
            ATTR_ATTRIBUTION: "Data provided by OpenCARWINGS",
            "last_connection": car.get("last_connection"),
            "signal_level": car.get("signal_level"),
            "soc": ev.get("soc"),
            "range_acoff": ev.get("range_acoff"),
        }


class CarVINSensor(OpenCarwingsCarEntity, SensorEntity):
    """The car's VIN."""

    _attr_icon = "mdi:identifier"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: dict | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_vin_{vin}"
        self._attr_translation_key = "vin"

    @property
    def native_value(self) -> str:
        return self._vin or "unknown"


class CarLastUpdatedSensor(OpenCarwingsCarEntity, SensorEntity):
    """When the car last reported, not when we last polled."""

    _attr_icon = "mdi:cloud-download-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: dict | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_last_updated_{vin}"
        self._attr_translation_key = "last_updated"

    def _timestamp(self) -> datetime | None:
        car = self._get_car()
        ev = car.get("ev_info") or {}
        loc = car.get("location") or {}
        ts = ev.get("last_updated") or loc.get("last_updated") or car.get("last_connection")
        return _ensure_aware(_parse_ts(ts) if isinstance(ts, str) else None)

    @property
    def native_value(self) -> datetime | None:
        return self._timestamp()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dt = self._timestamp()
        return {"relative": _relative_str(dt), "iso": _format_dt(dt)}


class CarLastRequestedSensor(OpenCarwingsCarEntity, SensorEntity):
    """When a command was last sent to the car."""

    _attr_icon = "mdi:cloud-upload-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: dict | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_last_requested_{vin}"
        self._attr_translation_key = "last_requested"

    def _timestamp(self) -> datetime | None:
        ts = self._get_car().get("command_request_time")
        return _ensure_aware(_parse_ts(ts) if isinstance(ts, str) else ts)

    @property
    def native_value(self) -> datetime | None:
        return self._timestamp()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        car = self._get_car()
        dt = self._timestamp()
        return {
            "relative": _relative_str(dt),
            "iso": _format_dt(dt),
            "command": car.get("command_type_display"),
            "result": car.get("command_result_display"),
        }


class CarListSensor(SensorEntity):
    """How many cars this account has."""

    _attr_icon = "mdi:car-multiple"

    def __init__(self, entry_id: str, cars: list[dict] | None = None, coordinator=None) -> None:
        self._entry_id = entry_id
        self._coordinator = coordinator
        self._cars = cars or []
        self._attr_unique_id = f"ha_opencarwings_{entry_id}_cars"

    @property
    def name(self) -> str:
        return "OpenCARWINGS Cars"

    @property
    def native_value(self) -> int:
        cars = self._coordinator.data if self._coordinator and self._coordinator.data is not None else self._cars
        return len(cars)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cars = self._coordinator.data if self._coordinator and self._coordinator.data is not None else self._cars
        return {
            ATTR_ATTRIBUTION: "Data provided by OpenCARWINGS",
            "car_vins": [c.get("vin") for c in cars if c.get("vin")],
        }

    async def async_added_to_hass(self) -> None:
        if self._coordinator:
            unsub = self._coordinator.async_add_listener(self.async_write_ha_state)
            self.async_on_remove(unsub)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    cars = coordinator.data if coordinator and coordinator.data is not None else data.get("cars", [])

    entities: list[SensorEntity] = []
    entities.append(CarListSensor(entry.entry_id, cars=cars, coordinator=coordinator))

    for car in cars:
        vin = car.get("vin")
        if not vin:
            continue

        for spec in CAR_SENSORS:
            entities.append(CarValueSensor(coordinator, entry.entry_id, vin, spec, seed_car=car))

        entities.append(CarStatusSensor(coordinator, entry.entry_id, vin, seed_car=car))

        entities.append(CarLastUpdatedSensor(coordinator, entry.entry_id, vin, seed_car=car))
        entities.append(CarLastRequestedSensor(coordinator, entry.entry_id, vin, seed_car=car))
        entities.append(CarVINSensor(coordinator, entry.entry_id, vin, seed_car=car))

    async_add_entities(entities)
