"""Sensor platform for OpenCARWINGS listing cars."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION, PERCENTAGE
from homeassistant.helpers.update_coordinator import CoordinatorEntity

try:
    from homeassistant.helpers.entity import EntityCategory
except Exception:  # pragma: no cover
    class EntityCategory:  # type: ignore
        DIAGNOSTIC = "diagnostic"

try:
    from homeassistant.components.sensor import SensorDeviceClass
except Exception:  # pragma: no cover
    class SensorDeviceClass:  # type: ignore
        BATTERY = "battery"
        TIMESTAMP = "timestamp"
        DURATION = "duration"

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


# -----------------------------
# Helpers
# -----------------------------

def _parse_ts(value: str | None):
    if not value:
        return None
    try:
        # support ISO8601 like `2026-01-04T12:00:00Z` or with microseconds `...10.419903Z`
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

# -----------------------------
# Base per-car entity
# -----------------------------

class OpenCarwingsCarEntity(CoordinatorEntity):
    """Base entity for a single car identified by VIN.

    - merges seed car dict (from initial cars list) with coordinator car dict
      so fields like odometer don't disappear if coordinator payload is missing them
    """

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: dict | None = None) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._vin = vin
        self._seed_car = seed_car or {}

    def _get_car(self) -> dict:
        # Merge: seed -> coordinator (coordinator wins, seed fills missing fields)
        if self.coordinator and getattr(self.coordinator, "data", None):
            for c in self.coordinator.data:
                if c.get("vin") == self._vin:
                    return {**self._seed_car, **(c or {})}
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



@dataclass(frozen=True)
class CarSensorSpec:
    key: str
    name: str
    value: Callable[[dict], Any]
    transform: Optional[Callable[[Any], Any]] = None
    device_class: Optional[str] = None
    unit_of_measurement: Optional[str] = None
    icon: Optional[str] = None


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None


def _plugged_to_str(v: Any) -> str:
    return "plugged" if bool(v) else "unplugged"


CAR_SENSORS: list[CarSensorSpec] = [
    CarSensorSpec(
        "range_acon",
        "Range (A/C on)",
        _ev_getter("range_acon"),
        transform=_to_float,
        unit_of_measurement="km",
        icon="mdi:map-marker-distance",
    ),
    CarSensorSpec(
        "range_acoff",
        "Range (A/C off)",
        _ev_getter("range_acoff"),
        transform=_to_float,
        unit_of_measurement="km",
        icon="mdi:map-marker-distance",
    ),
    CarSensorSpec("soc", "State of Charge", _ev_getter("soc"), transform=_round_1, device_class=SensorDeviceClass.BATTERY, unit_of_measurement=PERCENTAGE),
    CarSensorSpec("soc_display", "State of Charge Display", _ev_getter("soc_display"), transform=_round_1, device_class=SensorDeviceClass.BATTERY, unit_of_measurement=PERCENTAGE),
    CarSensorSpec("charge_bars", "Charge Bars", _ev_getter("charge_bars"), icon="mdi:battery-charging-medium"),
    CarSensorSpec("plugged_in", "Charge Cable", _ev_getter("plugged_in"), transform=_plugged_to_str, icon="mdi:ev-plug-type1"),
    CarSensorSpec("charging", "Charging", _ev_getter("charging"), icon="mdi:battery-charging"),
    CarSensorSpec("charge_finish", "Charge Finish", _ev_getter("charge_finish"), icon="mdi:battery-check"),
    CarSensorSpec("quick_charging", "Quick Charging", _ev_getter("quick_charging"), icon="mdi:ev-station"),
    CarSensorSpec("ac_status", "AC Status", _ev_getter("ac_status"), icon="mdi:air-conditioner"),
    CarSensorSpec("eco_mode", "Eco Mode", _ev_getter("eco_mode"), icon="mdi:leaf"),
    CarSensorSpec("car_running", "Running", _ev_getter("car_running"), icon="mdi:car-electric"),
    CarSensorSpec("odometer", "Odometer", lambda car: car.get("odometer"), transform=_to_int, unit_of_measurement="km", icon="mdi:counter"),
    CarSensorSpec(
        "full_chg_time",
        "Charge Time (3kW)",
        _ev_getter("full_chg_time"),
        transform=_chg_minutes,
        device_class=SensorDeviceClass.DURATION,
        unit_of_measurement="min",
        icon="mdi:timer-sand",
    ),
    CarSensorSpec(
        "limit_chg_time",
        "Charge Time (1.4kW)",
        _ev_getter("limit_chg_time"),
        transform=_chg_minutes,
        device_class=SensorDeviceClass.DURATION,
        unit_of_measurement="min",
        icon="mdi:timer-sand",
    ),
    CarSensorSpec(
        "obc_6kw",
        "Charge Time (6.6kW)",
        _ev_getter("obc_6kw"),
        transform=_chg_minutes,
        device_class=SensorDeviceClass.DURATION,
        unit_of_measurement="min",
        icon="mdi:timer-sand",
    ),
]


class CarValueSensor(OpenCarwingsCarEntity, SensorEntity):
    """Generic per-car sensor based on CarSensorSpec."""

    def __init__(self, coordinator, entry_id: str, vin: str, spec: CarSensorSpec, seed_car: dict | None = None) -> None:
        OpenCarwingsCarEntity.__init__(self, coordinator, entry_id, vin, seed_car)
        self._spec = spec
        self._attr_unique_id = f"ha_opencarwings_{spec.key}_{vin}"
        if spec.device_class:
            self._attr_device_class = spec.device_class
        if spec.icon:
            self._attr_icon = spec.icon
        if spec.unit_of_measurement:
            self._attr_native_unit_of_measurement = spec.unit_of_measurement

    @property
    def name(self) -> str:
        car = self._get_car()
        prefix = car.get("nickname") or car.get("model_name") or "Car"
        return f"{prefix} {self._spec.name}"

    @property
    def native_value(self):
        car = self._get_car()
        val = self._spec.value(car)

        if self._spec.transform:
            return self._spec.transform(val)
        return val


# -----------------------------
# Status sensor 
# -----------------------------

class CarStatusSensor(OpenCarwingsCarEntity, SensorEntity):
    """High-level status string for the car (charging, running, ac_on, idle)."""

    _attr_icon = "mdi:car-info"

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: dict | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_status_{vin}"

    @property
    def name(self) -> str:
        car = self._get_car()
        prefix = car.get("nickname") or car.get("model_name") or "Car"
        return f"{prefix} Status"

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
        # Keep this SMALL and SAFE (optional). Remove entirely if you want no attributes.
        car = self._get_car()
        ev = car.get("ev_info", {}) or {}
        return {
            ATTR_ATTRIBUTION: "Data provided by OpenCARWINGS",
            "last_connection": car.get("last_connection"),
            "signal_level": car.get("signal_level"),
            "soc": ev.get("soc"),
            "range_acoff": ev.get("range_acoff"),
        }


# -----------------------------
# Diagnostic sensors
# -----------------------------

class CarVINSensor(OpenCarwingsCarEntity, SensorEntity):
    """Per-car diagnostic sensor reporting the VIN."""

    _attr_icon = "mdi:identifier"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: dict | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_vin_{vin}"

    @property
    def name(self) -> str:
        car = self._get_car()
        prefix = car.get("nickname") or car.get("model_name") or "Car"
        return f"{prefix} VIN"

    @property
    def native_value(self) -> str:
        return self._vin or "unknown"


class CarLastUpdatedSensor(OpenCarwingsCarEntity, SensorEntity):
    """Diagnostic: timestamp provided by the car (ev_info.last_updated or location or last_connection)."""

    _attr_icon = "mdi:cloud-download-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: dict | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_last_updated_{vin}"

    @property
    def name(self) -> str:
        car = self._get_car()
        prefix = car.get("nickname") or car.get("model_name") or "Car"
        return f"{prefix} Last Updated"

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
    """Diagnostic: last command sent to the car, not the polling clock."""

    _attr_icon = "mdi:cloud-upload-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: dict | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_last_requested_{vin}"

    @property
    def name(self) -> str:
        car = self._get_car()
        prefix = car.get("nickname") or car.get("model_name") or "Car"
        return f"{prefix} Last Requested"

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


# -----------------------------
# Car list sensor
# -----------------------------

class CarListSensor(SensorEntity):
    """Sensor that represents the list of cars for the account."""

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


# -----------------------------
# Setup
# -----------------------------

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

        # Generic value sensors
        for spec in CAR_SENSORS:
            entities.append(CarValueSensor(coordinator, entry.entry_id, vin, spec, seed_car=car))

        # Status
        entities.append(CarStatusSensor(coordinator, entry.entry_id, vin, seed_car=car))

        # Diagnostics
        entities.append(CarLastUpdatedSensor(coordinator, entry.entry_id, vin, seed_car=car))
        entities.append(CarLastRequestedSensor(coordinator, entry.entry_id, vin, seed_car=car))
        entities.append(CarVINSensor(coordinator, entry.entry_id, vin, seed_car=car))

    async_add_entities(entities)
