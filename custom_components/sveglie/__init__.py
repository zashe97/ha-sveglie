"""Sveglie: sveglie vocali in stile Alexa per i satelliti di Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .dispositivi import dispositivo_del_gruppo
from .frasi import async_registra_frasi
from .scheda import async_registra_scheda
from .manager import GestoreSveglie

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR, Platform.SWITCH, Platform.TIME]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Avvia il gestore delle sveglie."""
    gestore = GestoreSveglie(hass, entry)
    hass.data[DOMAIN] = gestore
    await gestore.async_carica()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(async_registra_frasi(hass))
    integrazione = await async_get_integration(hass, DOMAIN)
    await async_registra_scheda(hass, str(integrazione.version))
    entry.async_on_unload(entry.add_update_listener(_async_aggiornata))

    @callback
    def _dispositivo_rinominato(evento: Event[dr.EventDeviceRegistryUpdatedData]) -> None:
        # nome del gruppo e entity_id delle sveglie seguono il nome del dispositivo
        if evento.data["action"] == "update" and (
            {"name", "name_by_user"} & set(evento.data.get("changes", {}))
        ):
            gestore.sincronizza()

    entry.async_on_unload(
        hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _dispositivo_rinominato)
    )
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


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Si può togliere un gruppo "Sveglie <satellite>" solo se non ha sveglie."""
    satellite = dispositivo_del_gruppo(device)
    if satellite is None:
        return False
    gestore: GestoreSveglie | None = hass.data.get(DOMAIN)
    return not (gestore and any(s.device_id == satellite for s in gestore.sveglie.values()))
