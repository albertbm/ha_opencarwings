from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

try:
    from homeassistant.const import CONF_API_KEY
except ImportError:  # pragma: no cover - older stubs
    CONF_API_KEY = "api_key"

from .api import DEFAULT_API_BASE, AuthenticationError

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
# Used when the selector helper is missing.
SCAN_INTERVAL_OPTIONS = [c[0] for c in SCAN_INTERVAL_CHOICES]
DEFAULT_SCAN_INTERVAL_MIN = 15

DEFAULT_API_BASE_URL = DEFAULT_API_BASE

from . import CONF_COMMAND_PIN


def _entry_title(api_base: str) -> str:
    """Name an entry after the server it talks to."""
    host = (api_base or "").split("://")[-1].strip("/") or DEFAULT_API_BASE_URL
    return f"OpenCARWINGS - {host}"


def _scan_selector():
    try:
        from homeassistant.helpers import selector

        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[{"value": v, "label": l} for v, l in SCAN_INTERVAL_CHOICES]
            )
        )
    except Exception:
        # The test stubs have no selector helper.
        return vol.In(SCAN_INTERVAL_OPTIONS)


def _secret_selector():
    try:
        from homeassistant.helpers import selector

        return selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )
    except Exception:
        return str


async def _async_check_api_key(hass, api_base: str, api_key: str) -> None:
    """Ask the server whether this key works. Raises AuthenticationError if not."""
    import opencarwings_client

    from .api import get_client

    client = await hass.async_add_executor_job(get_client, hass, api_base, api_key)
    try:
        async with client:
            await opencarwings_client.CarsApi(client).api_car_list()
    except opencarwings_client.ApiException as err:
        if getattr(err, "status", None) in (401, 403):
            raise AuthenticationError(err)
        raise


class OpenCARWINGSConfigFlow(config_entries.ConfigFlow, domain="ha_opencarwings"):
    """Config flow for OpenCARWINGS."""

    VERSION = 2

    def __init__(self) -> None:
        self._reauth_entry = None

    async def async_step_user(self, user_input=None):
        """Take an API key and check it before writing the entry."""
        errors = {}
        if user_input is not None:
            api_key = (user_input.get(CONF_API_KEY) or "").strip()
            api_base = user_input.get("api_base_url", DEFAULT_API_BASE_URL)

            try:
                await _async_check_api_key(getattr(self, "hass", None), api_base, api_key)
            except AuthenticationError:
                errors["base"] = "auth"
            except Exception:  # pragma: no cover - fallback
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=_entry_title(api_base),
                    data={
                        CONF_API_KEY: api_key,
                        "scan_interval": user_input.get("scan_interval", DEFAULT_SCAN_INTERVAL_MIN),
                        "api_base_url": api_base,
                        CONF_COMMAND_PIN: user_input.get(CONF_COMMAND_PIN, ""),
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): _secret_selector(),
                vol.Required("scan_interval", default=DEFAULT_SCAN_INTERVAL_MIN): _scan_selector(),
                vol.Required("api_base_url", default=DEFAULT_API_BASE_URL): str,
                vol.Optional(CONF_COMMAND_PIN, default=""): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    async def async_step_reauth(self, entry_data=None):
        """Entries set up with a username and password land here after upgrading."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Ask for an API key to replace the stored sign-in."""
        errors = {}
        entry = self._reauth_entry
        api_base = (entry.options or {}).get(
            "api_base_url", entry.data.get("api_base_url", DEFAULT_API_BASE_URL)
        )

        if user_input is not None:
            api_key = (user_input.get(CONF_API_KEY) or "").strip()
            try:
                await _async_check_api_key(self.hass, api_base, api_key)
            except AuthenticationError:
                errors["base"] = "auth"
            except Exception:  # pragma: no cover - fallback
                errors["base"] = "unknown"
            else:
                data = {
                    k: v
                    for k, v in entry.data.items()
                    if k not in ("username", "password", "access_token", "refresh_token")
                }
                data[CONF_API_KEY] = api_key
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): _secret_selector()}),
        )

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
            # The key lives in the entry data, not the options, so it goes there.
            api_key = (user_input.pop(CONF_API_KEY, "") or "").strip()

            if api_key:
                api_base = user_input.get("api_base_url", DEFAULT_API_BASE_URL)
                try:
                    await _async_check_api_key(self.hass, api_base, api_key)
                except AuthenticationError:
                    errors["base"] = "auth"
                except Exception:  # pragma: no cover - fallback
                    errors["base"] = "unknown"
                else:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        title=_entry_title(api_base),
                        data={**self.config_entry.data, CONF_API_KEY: api_key},
                    )

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        current_scan = self.config_entry.options.get("scan_interval", self.config_entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL_MIN))
        current_api = self.config_entry.options.get("api_base_url", self.config_entry.data.get("api_base_url", DEFAULT_API_BASE_URL))
        current_pin = self.config_entry.options.get(CONF_COMMAND_PIN, self.config_entry.data.get(CONF_COMMAND_PIN, ""))

        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema({
                vol.Optional(CONF_API_KEY, default=""): _secret_selector(),
                vol.Required("scan_interval", default=current_scan): _scan_selector(),
                vol.Required("api_base_url", default=current_api): str,
                vol.Optional(CONF_COMMAND_PIN, default=current_pin): str,
            }),
        )
