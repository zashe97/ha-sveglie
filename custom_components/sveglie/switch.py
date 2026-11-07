"""Interruttori di ogni sveglia: accesa, volume progressivo, salta festivi, salta la prossima."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entita import EntitaSveglia, imposta_piattaforma


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    imposta_piattaforma(
        hass,
        entry,
        async_add_entities,
        lambda g, sid: [
            InterruttoreSveglia(g, sid, "attiva", "attiva", "mdi:alarm"),
            InterruttoreSveglia(g, sid, "progressiva", "progressiva", "mdi:volume-plus"),
            InterruttoreSveglia(g, sid, "salta_festivi", "salta_festivi", "mdi:calendar-remove"),
            SaltaProssima(g, sid),
        ],
    )


class InterruttoreSveglia(EntitaSveglia, SwitchEntity):
    """Un campo sì/no della sveglia."""

    def __init__(self, gestore, sid, chiave: str, campo: str, icona: str) -> None:
        super().__init__(gestore, sid, chiave)
        self._campo = campo
        self._attr_icon = icona
        # categoria "configurazione": HA non le espone da sole all'assistente vocale
        # (a voce si usano gli strumenti sveglie__*, non serve gonfiare il prompt)
        self._attr_entity_category = EntityCategory.CONFIG

    @callback
    def _aggiorna_attributi(self) -> None:
        sv = self.sveglia
        self._attr_is_on = bool(getattr(sv, self._campo)) if sv else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._modifica(**{self._campo: True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._modifica(**{self._campo: False})


class SaltaProssima(EntitaSveglia, SwitchEntity):
    """Acceso = la prossima suonata viene saltata (si spegne da solo dopo)."""

    _attr_icon = "mdi:debug-step-over"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, gestore, sid) -> None:
        super().__init__(gestore, sid, "salta_prossima")

    @callback
    def _aggiorna_attributi(self) -> None:
        sv = self.sveglia
        self._attr_is_on = bool(sv.salta) if sv else None
        self._attr_extra_state_attributes = {"data_saltata": sv.salta if sv else None}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._modifica(salta_prossima=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._modifica(salta_prossima=False)
