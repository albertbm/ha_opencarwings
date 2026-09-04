from ..helpers.entity import Entity


class BinarySensorDeviceClass:
    BATTERY_CHARGING = "battery_charging"
    PLUG = "plug"
    RUNNING = "running"
    PROBLEM = "problem"


class BinarySensorEntity(Entity):
    """Minimal BinarySensorEntity stub."""

    @property
    def is_on(self):
        return None

    @property
    def unique_id(self):
        return getattr(self, "_attr_unique_id", None)

    @property
    def name(self):
        return getattr(self, "_attr_name", None)
