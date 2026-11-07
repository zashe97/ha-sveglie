"""Un dispositivo "Sveglie <nome>" per ogni satellite vocale, con dentro le sue sveglie."""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN

PREFISSO_GRUPPO = "dispositivo_"


@callback
def satelliti(hass: HomeAssistant) -> list[str]:
    """I dispositivi che hanno un satellite vocale (Echo con hassmic, Voice PE, ESPHome...)."""
    trovati: list[str] = []
    for voce in er.async_get(hass).entities.values():
        if voce.domain == "assist_satellite" and voce.device_id and not voce.disabled_by:
            if voce.device_id not in trovati:
                trovati.append(voce.device_id)
    return trovati


@callback
def nome_dispositivo(hass: HomeAssistant, device_id: str | None) -> str | None:
    if not device_id or (dev := dr.async_get(hass).async_get(device_id)) is None:
        return None
    return dev.name_by_user or dev.name


@callback
def id_gruppo(device_id: str) -> tuple[str, str]:
    return (DOMAIN, f"{PREFISSO_GRUPPO}{device_id}")


@callback
def assicura_gruppo(
    hass: HomeAssistant, entry: ConfigEntry, device_id: str | None
) -> dr.DeviceEntry | None:
    """Crea (o aggiorna il nome di) "Sveglie <dispositivo>", collegato al dispositivo vero."""
    if (nome := nome_dispositivo(hass, device_id)) is None:
        return None
    assert device_id is not None
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        config_subentry_id=None,
        identifiers={id_gruppo(device_id)},
        name=f"Sveglie {nome}",
        manufacturer="Sveglie",
        model="Sveglie del dispositivo",
        entry_type=dr.DeviceEntryType.SERVICE,
        via_device_id=device_id,
    )


@callback
def assicura_gruppi(hass: HomeAssistant, entry: ConfigEntry, altri: Iterable[str | None]) -> list[str]:
    """Un gruppo per ogni satellite e per ogni dispositivo che ha sveglie. Ritorna i device_id."""
    fatti: list[str] = []
    for device_id in [*satelliti(hass), *altri]:
        if device_id and device_id not in fatti and assicura_gruppo(hass, entry, device_id):
            fatti.append(device_id)
    return fatti


@callback
def dispositivo_del_gruppo(device: dr.DeviceEntry) -> str | None:
    """Il device_id del satellite a cui appartiene un gruppo, None se non è un gruppo."""
    for dominio, ident in device.identifiers:
        if dominio == DOMAIN and ident.startswith(PREFISSO_GRUPPO):
            return ident[len(PREFISSO_GRUPPO):]
    return None
