"""Sensore 'Prossima sveglia' con l'elenco completo negli attributi."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SEGNALE_AGGIORNATE
from .logic import descrivi


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([ProssimaSveglia(entry)])


class ProssimaSveglia(SensorEntity):
    """Quando suona la prossima sveglia."""

    _attr_has_entity_name = True
    _attr_translation_key = "prossima"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:alarm"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}_prossima"
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Sveglie",
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SEGNALE_AGGIORNATE, self._aggiorna)
        )
        self._aggiorna()

    @callback
    def _aggiorna(self) -> None:
        gestore = self.hass.data.get(DOMAIN)
        elenco = gestore.elenco() if gestore else []
        adesso = dt_util.now()
        self._attr_native_value = (
            datetime.fromisoformat(elenco[0].prossima) if elenco and elenco[0].prossima else None
        )
        disp = dr.async_get(self.hass)
        righe = []
        for s in elenco:
            dev = disp.async_get(s.device_id) if s.device_id else None
            righe.append(
                {
                    "descrizione": descrivi(s, adesso, gestore.tz),
                    "prossima": s.prossima,
                    "ora": s.ora,
                    "giorni": s.giorni,
                    "nome": s.nome,
                    "dispositivo": (dev.name_by_user or dev.name) if dev else None,
                }
            )
        self._attr_extra_state_attributes = {"sveglie": righe, "numero": len(righe)}
        self.async_write_ha_state()
