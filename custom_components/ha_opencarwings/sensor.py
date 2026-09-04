"""Sensor platform for the car's readings and diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPressure,
    UnitOfTemperature,
)

try:
    from homeassistant.helpers.entity import EntityCategory
except Exception:  # pragma: no cover
    class EntityCategory:  # type: ignore
        DIAGNOSTIC = "diagnostic"

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from . import DOMAIN
from .entity import OpenCarwingsCarEntity, async_add_cars
from .util import CarData

_LOGGER = logging.getLogger(__name__)


def _parse_ts(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
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


def _flat(car: CarData) -> dict:
    return car.as_dict()


def _ev_getter(key: str, fallback: str | None = None) -> Callable[[CarData], Any]:
    """Read ev_info[key], then the fallback or key on the car itself."""
    def _get(car: CarData):
        car = _flat(car)
        ev = car.get("ev_info") or {}
        if isinstance(ev, dict) and key in ev:
            return ev.get(key)
        if fallback:
            return car.get(fallback)
        return car.get(key)
    return _get

def _health_getter(key: str) -> Callable[[CarData], Any]:
    """Read a field out of the vehicle health report."""
    def _get(car: CarData):
        return (_flat(car).get("veh_health") or {}).get(key)
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


# The server decodes the cabin byte as temp/2 - 40, leaving 0 when the car sent
# nothing and 87.5 for the TCU's 0xFF marker. A real 0 C reads as unknown too.
_CABIN_TEMP_NO_DATA = (0.0, 87.5)


def _cabin_temp(v: Any) -> float | None:
    """Cabin temperature in C, or None when the car did not report one."""
    temp = _to_float(v)
    if temp is None or temp in _CABIN_TEMP_NO_DATA:
        return None
    return temp


def _code_list(v: Any) -> list[str]:
    """Fault codes as readable strings.

    The server sends one entry per affected ECU, with the decoded code.
    """
    if not v:
        return []
    if isinstance(v, dict):
        v = list(v.values())
    if not isinstance(v, (list, tuple)):
        v = [v]

    codes = []
    for entry in v:
        if isinstance(entry, dict):
            code = entry.get("code_label") or entry.get("code")
            ecu = entry.get("ecu_label")
            if not code:
                continue
            codes.append(f"{code} ({ecu})" if ecu else str(code))
        elif entry:
            codes.append(str(entry))
    return codes


def _tyre_pressure(v: Any) -> int | None:
    """Tyre pressure in kPa. The server sends 0 for a wheel it has no reading for."""
    kpa = _to_int(v)
    if kpa is None or kpa <= 0:
        return None
    return kpa


def _round_1(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return round(float(v), 1)
    except Exception:
        return None


# Gear values as the server stores them.
CAR_GEAR = {0: "park", 1: "drive", 2: "reverse"}

# The two telematics units Nissan shipped.
TCU_TYPES = ("continental2012", "ficosa2016")


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
    value: Callable[[CarData], Any]
    transform: Optional[Callable[[Any], Any]] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    unit_of_measurement: Optional[str] = None
    suggested_unit: Optional[str] = None
    display_precision: Optional[int] = None
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
        display_precision=0,
        icon="mdi:map-marker-distance",
    ),
    CarSensorSpec(
        "range_acoff",
        _ev_getter("range_acoff"),
        transform=_to_float,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_of_measurement=UnitOfLength.KILOMETERS,
        display_precision=0,
        icon="mdi:map-marker-distance",
    ),
    CarSensorSpec("soc", _ev_getter("soc"), transform=_round_1, device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT, unit_of_measurement=PERCENTAGE),
    CarSensorSpec("soc_display", _ev_getter("soc_display"), transform=_round_1, device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT, unit_of_measurement=PERCENTAGE),
    CarSensorSpec("charge_bars", _ev_getter("charge_bars"), icon="mdi:battery-charging-medium"),
    CarSensorSpec(
        "cabin_temp",
        _ev_getter("cabin_temp"),
        transform=_cabin_temp,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_of_measurement=UnitOfTemperature.CELSIUS,
        display_precision=0,
        icon="mdi:car-seat-heater",
    ),
    CarSensorSpec(
        "odometer",
        lambda car: _flat(car).get("odometer"),
        transform=_positive_int,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        unit_of_measurement=UnitOfLength.KILOMETERS,
        display_precision=0,
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
        lambda car: _flat(car).get("signal_level"),
        transform=_to_int,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
        diagnostic=True,
    ),
    CarSensorSpec(
        "carrier",
        lambda car: _flat(car).get("carrier"),
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
    CarSensorSpec(
        "tpms_fl",
        _health_getter("tpms_fl"),
        transform=_tyre_pressure,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_of_measurement=UnitOfPressure.KPA,
        display_precision=0,
        icon="mdi:car-tire-alert",
    ),
    CarSensorSpec(
        "tpms_fr",
        _health_getter("tpms_fr"),
        transform=_tyre_pressure,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_of_measurement=UnitOfPressure.KPA,
        display_precision=0,
        icon="mdi:car-tire-alert",
    ),
    CarSensorSpec(
        "tpms_rl",
        _health_getter("tpms_rl"),
        transform=_tyre_pressure,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_of_measurement=UnitOfPressure.KPA,
        display_precision=0,
        icon="mdi:car-tire-alert",
    ),
    CarSensorSpec(
        "tpms_rr",
        _health_getter("tpms_rr"),
        transform=_tyre_pressure,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_of_measurement=UnitOfPressure.KPA,
        display_precision=0,
        icon="mdi:car-tire-alert",
    ),
    CarSensorSpec(
        "tcu_type",
        lambda car: _flat(car).get("tcu_type"),
        transform=_text,
        device_class=SensorDeviceClass.ENUM,
        options=TCU_TYPES,
        icon="mdi:chip",
        diagnostic=True,
    ),
]


class CarValueSensor(OpenCarwingsCarEntity, SensorEntity):
    """One value from CAR_SENSORS."""

    def __init__(self, coordinator, entry_id: str, vin: str, spec: CarSensorSpec, seed_car: CarData | None = None) -> None:
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
        if spec.display_precision is not None:
            self._attr_suggested_display_precision = spec.display_precision
        if spec.options:
            self._attr_options = list(spec.options)
        if spec.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        val = self._spec.value(self._get_car())

        if self._spec.transform:
            return self._spec.transform(val)
        return val


class CarStatusSensor(OpenCarwingsCarEntity, SensorEntity):
    """High-level status string for the car (charging, running, ac_on, idle)."""

    _attr_icon = "mdi:car-info"

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_status_{vin}"
        self._attr_translation_key = "status"

    @property
    def native_value(self) -> str:
        car = self._get_car_dict()
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
        car = self._get_car_dict()
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

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None) -> None:
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

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_last_updated_{vin}"
        self._attr_translation_key = "last_updated"

    def _timestamp(self) -> datetime | None:
        car = self._get_car().get_latest_car()
        if car is None:
            return None
        ts = (
            getattr(car.ev_info, "last_updated", None)
            or getattr(car.location, "last_updated", None)
            or car.last_connection
        )
        if isinstance(ts, str):
            ts = _parse_ts(ts)
        return _ensure_aware(ts if isinstance(ts, datetime) else None)

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

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_last_requested_{vin}"
        self._attr_translation_key = "last_requested"

    def _timestamp(self) -> datetime | None:
        ts = self._get_car_dict().get("command_request_time")
        if isinstance(ts, str):
            ts = _parse_ts(ts)
        return _ensure_aware(ts if isinstance(ts, datetime) else None)

    @property
    def native_value(self) -> datetime | None:
        return self._timestamp()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        car = self._get_car_dict()
        dt = self._timestamp()
        return {
            "relative": _relative_str(dt),
            "iso": _format_dt(dt),
            "command": car.get("command_type_display"),
            "result": car.get("command_result_display"),
        }


class CarDiagnosticTroubleCodesSensor(OpenCarwingsCarEntity, SensorEntity):
    """How many fault codes the car is storing, with the codes as attributes."""

    _attr_icon = "mdi:car-wrench"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_dtc_{vin}"
        self._attr_translation_key = "dtc"

    def _health(self) -> dict:
        return self._get_car_dict().get("veh_health") or {}

    @property
    def native_value(self) -> int | None:
        health = self._health()
        if not health:
            return None
        return len(_code_list(health.get("dtc_short"))) + len(_code_list(health.get("dtc_long")))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        health = self._health()
        ts = _ensure_aware(_parse_ts(health.get("dtc_timestamp")))
        return {
            "short_codes": _code_list(health.get("dtc_short")),
            "long_codes": _code_list(health.get("dtc_long")),
            "read_at": _format_dt(ts),
            "report_updated": health.get("last_updated"),
        }


class CarListSensor(SensorEntity):
    """How many cars this account has."""

    _attr_icon = "mdi:car-multiple"

    def __init__(self, entry_id: str, cars: list[CarData] | None = None, coordinator=None) -> None:
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
            "car_vins": [c.vin for c in cars if c.vin],
        }

    async def async_added_to_hass(self) -> None:
        if self._coordinator:
            unsub = self._coordinator.async_add_listener(self.async_write_ha_state)
            self.async_on_remove(unsub)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    cars = coordinator.data if coordinator and coordinator.data is not None else data.get("cars", [])

    async_add_entities([CarListSensor(entry.entry_id, cars=cars, coordinator=coordinator)])

    def _build(car: dict) -> list[SensorEntity]:
        vin = car.vin
        entities: list[SensorEntity] = [
            CarValueSensor(coordinator, entry.entry_id, vin, spec, seed_car=car)
            for spec in CAR_SENSORS
        ]
        entities.append(CarStatusSensor(coordinator, entry.entry_id, vin, seed_car=car))
        entities.append(CarLastUpdatedSensor(coordinator, entry.entry_id, vin, seed_car=car))
        entities.append(CarLastRequestedSensor(coordinator, entry.entry_id, vin, seed_car=car))
        entities.append(CarVINSensor(coordinator, entry.entry_id, vin, seed_car=car))
        entities.append(
            CarDiagnosticTroubleCodesSensor(coordinator, entry.entry_id, vin, seed_car=car)
        )
        return entities

    async_add_cars(hass, entry, async_add_entities, _build)
