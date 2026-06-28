"""Config flow for DTE Multi-Meter Usage."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DTEDataError, fetch_dte_xml, parse_dte_green_button_xml
from .const import DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class DTEMultiMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DTE Multi-Meter Usage."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL].strip()
            name = user_input.get(CONF_NAME, DEFAULT_NAME).strip() or DEFAULT_NAME

            for entry in self._async_current_entries():
                if entry.data.get(CONF_URL) == url:
                    return self.async_abort(reason="already_configured")

            try:
                session = async_get_clientsession(self.hass)
                xml_text = await fetch_dte_xml(session, url)
                parsed = parse_dte_green_button_xml(xml_text)
                if not parsed.meters:
                    raise DTEDataError("No electric or gas meters were found in the DTE XML.")
            except DTEDataError as err:
                _LOGGER.exception("DTE validation failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Unexpected DTE validation error: %s", err)
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=name,
                    data={CONF_NAME: name, CONF_URL: url},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(CONF_URL): str,
                }
            ),
            errors=errors,
        )
