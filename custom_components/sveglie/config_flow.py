"""Configurazione da interfaccia: nessun campo obbligatorio."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DISPOSITIVO_PREDEFINITO,
    CONF_MINUTI_POSTICIPO,
    CONF_RECUPERO_MINUTI,
    DEFAULT_MINUTI_POSTICIPO,
    DEFAULT_RECUPERO_MINUTI,
    DOMAIN,
)


class SveglieConfigFlow(ConfigFlow, domain=DOMAIN):
    """Aggiunge l'integrazione con un clic."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Sveglie", data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SveglieOptionsFlow()


class SveglieOptionsFlow(OptionsFlow):
    """Opzioni: dispositivo di riserva e minuti di posticipo."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        o = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DISPOSITIVO_PREDEFINITO,
                    description={"suggested_value": o.get(CONF_DISPOSITIVO_PREDEFINITO)},
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        entity=[selector.EntityFilterSelectorConfig(domain="assist_satellite")]
                    )
                ),
                vol.Required(
                    CONF_MINUTI_POSTICIPO,
                    default=o.get(CONF_MINUTI_POSTICIPO, DEFAULT_MINUTI_POSTICIPO),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=60, step=1, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_RECUPERO_MINUTI,
                    default=o.get(CONF_RECUPERO_MINUTI, DEFAULT_RECUPERO_MINUTI),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=120, step=1, mode=selector.NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
