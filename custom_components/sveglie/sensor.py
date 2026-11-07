"""Sensori: 'Prossima sveglia' (tutte) e la prossima suonata di ogni sveglia."""

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
from .entita import EntitaSveglia, imposta_piattaforma
from .logic import descrivi


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([ProssimaSveglia(entry)])
    imposta_piattaforma(hass, entry, async_add_entities, lambda g, sid: [ProssimaSuonata(g, sid)])


class ProssimaSveglia(SensorEntity):
    """Quando suona la prossima sveglia, con l'elenco completo negli attributi."""

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
        attive = [s for s in elenco if s.prossima]
        self._attr_native_value = datetime.fromisoformat(attive[0].prossima) if attive else None
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
                    "attiva": s.attiva,
                    "posticipata": s.posticipata,
                    "dispositivo": (dev.name_by_user or dev.name) if dev else None,
                }
            )
        self._attr_extra_state_attributes = {"sveglie": righe, "numero": len(righe)}
        self.async_write_ha_state()


class ProssimaSuonata(EntitaSveglia, SensorEntity):
    """Quando suonerà questa sveglia (vuoto se è spenta)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:alarm-check"

    def __init__(self, gestore, sid) -> None:
        super().__init__(gestore, sid, "prossima_suonata")

    @callback
    def _aggiorna_attributi(self) -> None:
        sv = self.sveglia
        self._attr_native_value = (
            datetime.fromisoformat(sv.prossima) if sv and sv.prossima else None
        )
        if sv:
            self._attr_extra_state_attributes = {
                "descrizione": descrivi(sv, dt_util.now(), self.gestore.tz),
                "giorni": sv.giorni,
                "durata_minuti": sv.durata or self.gestore.durata,
            }
