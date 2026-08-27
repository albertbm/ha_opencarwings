from ..helpers.entity import Entity


class NumberDeviceClass:
    TEMPERATURE = "temperature"


class NumberMode:
    AUTO = "auto"
    BOX = "box"
    SLIDER = "slider"


class NumberEntity(Entity):
    """Minimal NumberEntity stub."""

    @property
    def unique_id(self):
        return getattr(self, "_attr_unique_id", None)

    @property
    def native_value(self):
        return getattr(self, "_attr_native_value", None)

    async def async_set_native_value(self, value):
        raise NotImplementedError
