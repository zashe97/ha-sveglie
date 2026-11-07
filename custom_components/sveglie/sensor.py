"""Sensori: 'Prossima sveglia' (di tutta la casa e di ogni satellite) e la prossima suonata
di ogni sveglia."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .dispositivi import nome_dispositivo
from .entita import EntitaSveglia, imposta_piattaforma
from .logic import descrivi
from .manager import GestoreSveglie
from .vista import VistaSveglie, dispositivi_con_vista


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    gestore: GestoreSveglie = hass.data[DOMAIN]
    async_add_entities(
        [ProssimaSveglia(gestore, None)]
        + [ProssimaSveglia(gestore, d) for d in dispositivi_con_vista(hass, gestore)]
    )
    imposta_piattaforma(hass, entry, async_add_entities, lambda g, sid: [ProssimaSuonata(g, sid)])


class ProssimaSveglia(VistaSveglie, SensorEntity):
    """Quando suona la prossima sveglia, con l'elenco negli attributi. Solo lettura."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:alarm"

    def __init__(self, gestore: GestoreSveglie, device_id: str | None) -> None:
        super().__init__(gestore, device_id, "prossima")

    @callback
    def _aggiorna_attributi(self) -> None:
        elenco = self.sveglie()
        adesso = dt_util.now()
        attive = [s for s in elenco if s.prossima]
        self._attr_native_value = datetime.fromisoformat(attive[0].prossima) if attive else None
        righe = [
            {
                "descrizione": descrivi(s, adesso, self.gestore.tz),
                "prossima": s.prossima,
                "ora": s.ora,
                "giorni": s.giorni,
                "nome": s.nome,
                "attiva": s.attiva,
                "posticipata": s.posticipata,
                "dispositivo": nome_dispositivo(self.hass, s.device_id),
            }
            for s in elenco
        ]
        self._attr_extra_state_attributes = {"sveglie": righe, "numero": len(righe)}


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
                "dispositivo": nome_dispositivo(self.hass, sv.device_id),
            }
