from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .api import OpenCarWingsAPI, AuthenticationError, DEFAULT_API_BASE

# Scan interval choices in minutes with friendly labels
SCAN_INTERVAL_CHOICES = [
    (1, "1 minute"),
    (5, "5 minutes"),
    (10, "10 minutes"),
    (15, "15 minutes (default)"),
    (30, "30 minutes"),
    (60, "1 hour"),
    (180, "3 hours"),
    (360, "6 hours"),
    (720, "12 hours"),
    (1440, "1 day"),
]
# Values used when selector is not available (fallback)
SCAN_INTERVAL_OPTIONS = [c[0] for c in SCAN_INTERVAL_CHOICES]
DEFAULT_SCAN_INTERVAL_MIN = 15

# Default API base URL
DEFAULT_API_BASE_URL = DEFAULT_API_BASE

from . import CONF_COMMAND_PIN, CONF_GPS_MAX_RADIUS_KM, DEFAULT_GPS_MAX_RADIUS_KM


def _entry_title(username: str, api_base: str) -> str:
    """Title an entry with its account and server."""
    host = (api_base or "").split("://")[-1].strip("/") or DEFAULT_API_BASE_URL
    return f"{username} - {host}"


class OpenCARWINGSConfigFlow(config_entries.ConfigFlow, domain="ha_opencarwings"):
    """Config flow for OpenCARWINGS."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step where user provides credentials."""
        errors = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            api_base = user_input.get("api_base_url", DEFAULT_API_BASE_URL)

            client = OpenCarWingsAPI(getattr(self, "hass", None), base_url=api_base)
            try:
                tokens = await client.async_obtain_token(username, password)
            except AuthenticationError:
                errors["base"] = "auth"
            except Exception:  # pragma: no cover - fallback
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=_entry_title(username, api_base),
                    data={
                        "username": username,
                        "access_token": tokens.get("access"),
                        "refresh_token": tokens.get("refresh"),
                        # persist initial scan interval choice
                        "scan_interval": user_input.get("scan_interval", DEFAULT_SCAN_INTERVAL_MIN),
                        "api_base_url": api_base,
                        CONF_COMMAND_PIN: user_input.get(CONF_COMMAND_PIN, ""),
                        CONF_GPS_MAX_RADIUS_KM: user_input.get(
                            CONF_GPS_MAX_RADIUS_KM, DEFAULT_GPS_MAX_RADIUS_KM
                        ),
                    },
                )

        # Prefer to show a pretty select when Home Assistant's selector helpers
        # are available; fall back to a numeric choice list otherwise.
        try:
            from homeassistant.helpers import selector

            scan_selector = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": v, "label": l} for v, l in SCAN_INTERVAL_CHOICES]
                )
            )
        except Exception:
            # selector not available in minimal test stubs — use numeric options
            scan_selector = vol.In(SCAN_INTERVAL_OPTIONS)

        try:
            from homeassistant.helpers import selector

            radius_selector = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=2000, step=5, unit_of_measurement="km",
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        except Exception:
            radius_selector = vol.Coerce(float)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required("scan_interval", default=DEFAULT_SCAN_INTERVAL_MIN): scan_selector,
                vol.Required("api_base_url", default=DEFAULT_API_BASE_URL): str,
                vol.Optional(CONF_COMMAND_PIN, default=""): str,
                vol.Optional(
                    CONF_GPS_MAX_RADIUS_KM, default=DEFAULT_GPS_MAX_RADIUS_KM
                ): radius_selector,
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        try:
            self.config_entry = config_entry
        except AttributeError:
            pass

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            # A new password gets fresh tokens, which go in the entry data.
            password = (user_input.pop(CONF_PASSWORD, "") or "").strip()
            username = (user_input.pop(CONF_USERNAME, "") or "").strip()

            if password:
                api_base = user_input.get("api_base_url", DEFAULT_API_BASE_URL)
                client = OpenCarWingsAPI(self.hass, base_url=api_base)
                try:
                    tokens = await client.async_obtain_token(username, password)
                except AuthenticationError:
                    errors["base"] = "auth"
                except Exception:  # pragma: no cover - fallback
                    errors["base"] = "unknown"
                else:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        title=_entry_title(username, api_base),
                        data={
                            **self.config_entry.data,
                            "username": username,
                            "access_token": tokens.get("access"),
                            "refresh_token": tokens.get("refresh"),
                        },
                    )

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        current_scan = self.config_entry.options.get("scan_interval", self.config_entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL_MIN))
        current_api = self.config_entry.options.get("api_base_url", self.config_entry.data.get("api_base_url", DEFAULT_API_BASE_URL))
        current_user = self.config_entry.data.get(CONF_USERNAME, "")
        current_pin = self.config_entry.options.get(CONF_COMMAND_PIN, self.config_entry.data.get(CONF_COMMAND_PIN, ""))
        current_radius = self.config_entry.options.get(
            CONF_GPS_MAX_RADIUS_KM,
            self.config_entry.data.get(CONF_GPS_MAX_RADIUS_KM, DEFAULT_GPS_MAX_RADIUS_KM),
        )
        try:
            from homeassistant.helpers import selector

            scan_selector = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": v, "label": l} for v, l in SCAN_INTERVAL_CHOICES]
                )
            )
        except Exception:
            scan_selector = vol.In(SCAN_INTERVAL_OPTIONS)

        try:
            from homeassistant.helpers import selector

            radius_selector = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=2000, step=5, unit_of_measurement="km",
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        except Exception:
            radius_selector = vol.Coerce(float)

        try:
            from homeassistant.helpers import selector

            password_selector = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
        except Exception:
            password_selector = str

        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema({
                vol.Optional(CONF_USERNAME, default=current_user): str,
                vol.Optional(CONF_PASSWORD, default=""): password_selector,
                vol.Required("scan_interval", default=current_scan): scan_selector,
                vol.Required("api_base_url", default=current_api): str,
                vol.Optional(CONF_COMMAND_PIN, default=current_pin): str,
                vol.Optional(
                    CONF_GPS_MAX_RADIUS_KM, default=current_radius
                ): radius_selector,
            }),
        )

