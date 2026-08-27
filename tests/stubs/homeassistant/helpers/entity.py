class Entity:
    """Minimal entity base used in tests."""

    @property
    def name(self):
        raise NotImplementedError

    @property
    def unique_id(self):
        return None

    @property
    def extra_state_attributes(self):
        return {}

    @property
    def device_info(self):
        return {}

    @property
    def state(self):
        return None

    @property
    def device_class(self):
        return getattr(self, "_attr_device_class", None)

    @property
    def state_class(self):
        return getattr(self, "_attr_state_class", None)

    @property
    def native_unit_of_measurement(self):
        return getattr(self, "_attr_native_unit_of_measurement", None)

    @property
    def icon(self):
        return getattr(self, "_attr_icon", None)
