from ..helpers.entity import Entity

class SensorEntity(Entity):
    """Minimal SensorEntity stub for tests."""

    @property
    def native_value(self):
        return getattr(self, "_attr_native_value", None)

    @property
    def unique_id(self):
        return getattr(self, "_attr_unique_id", None)

    @property
    def name(self):
        return getattr(self, "_attr_name", None)

    @property
    def entity_category(self):
        return getattr(self, "_attr_entity_category", None)

    @property
    def suggested_display_precision(self):
        return getattr(self, "_attr_suggested_display_precision", None)


class SensorStateClass:
    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


class SensorDeviceClass:
    BATTERY = "battery"
    TIMESTAMP = "timestamp"
    DURATION = "duration"
    DISTANCE = "distance"
    ENERGY_STORAGE = "energy_storage"
    ENUM = "enum"
    PRESSURE = "pressure"
