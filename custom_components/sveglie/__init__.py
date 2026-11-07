"""Sveglie: sveglie vocali in stile Alexa per i satelliti di Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .frasi import async_registra_frasi
from .manager import GestoreSveglie

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.TIME]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Avvia il gestore delle sveglie."""
    gestore = GestoreSveglie(hass, entry)
    hass.data[DOMAIN] = gestore
    await gestore.async_carica()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(async_registra_frasi(hass))
    entry.async_on_unload(entry.add_update_listener(_async_aggiornata))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Ferma il gestore."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok and (gestore := hass.data.pop(DOMAIN, None)):
        gestore.async_scarica()
    return ok


async def _async_aggiornata(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Opzioni cambiate: si riparte. Sveglie aggiunte o modificate: si riallinea e basta."""
    gestore: GestoreSveglie | None = hass.data.get(DOMAIN)
    if gestore is None or dict(entry.options) != gestore.opzioni:
        await hass.config_entries.async_reload(entry.entry_id)
        return
    gestore.sincronizza()
