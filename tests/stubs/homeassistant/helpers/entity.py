class Entity:
    """Minimal entity base used in tests."""

    def async_write_ha_state(self):
        """Real Home Assistant gives every entity this; tests only need it to exist."""

    def async_on_remove(self, func):
        """Collect teardown callbacks the way Home Assistant does."""
        self._on_remove = getattr(self, "_on_remove", [])
        self._on_remove.append(func)

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
