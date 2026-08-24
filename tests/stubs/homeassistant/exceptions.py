class HomeAssistantError(Exception):
    """Minimal stub for Home Assistant's base error."""


class ConfigEntryError(HomeAssistantError):
    """Minimal stub for a config entry error."""


class ConfigEntryAuthFailed(ConfigEntryError):
    """Raised when an entry's credentials are no longer valid."""
