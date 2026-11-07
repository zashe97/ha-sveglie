"""Sveglie: sveglie vocali in stile Alexa per i satelliti di Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DISPOSITIVO_PREDEFINITO,
    CONF_MINUTI_POSTICIPO,
    CONF_RECUPERO_MINUTI,
    DEFAULT_MINUTI_POSTICIPO,
    DEFAULT_RECUPERO_MINUTI,
    DOMAIN,
)
from .frasi import async_registra_frasi
from .manager import GestoreSveglie

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Avvia il gestore delle sveglie."""
    opzioni = entry.options
    gestore = GestoreSveglie(
        hass,
        dispositivo_predefinito=opzioni.get(CONF_DISPOSITIVO_PREDEFINITO) or None,
        minuti_posticipo=int(opzioni.get(CONF_MINUTI_POSTICIPO, DEFAULT_MINUTI_POSTICIPO)),
        recupero_minuti=int(opzioni.get(CONF_RECUPERO_MINUTI, DEFAULT_RECUPERO_MINUTI)),
    )
    await gestore.async_carica()
    hass.data[DOMAIN] = gestore
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(async_registra_frasi(hass))
    entry.async_on_unload(entry.add_update_listener(_async_opzioni_cambiate))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Ferma il gestore."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok and (gestore := hass.data.pop(DOMAIN, None)):
        gestore.async_scarica()
    return ok


async def _async_opzioni_cambiate(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
