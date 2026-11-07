"""L'ora di ogni sveglia, modificabile dalla dashboard."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entita import EntitaSveglia, imposta_piattaforma


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    imposta_piattaforma(hass, entry, async_add_entities, lambda g, sid: [OraSveglia(g, sid)])


class OraSveglia(EntitaSveglia, TimeEntity):
    """Ora della sveglia."""

    _attr_icon = "mdi:clock-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, gestore, sid) -> None:
        super().__init__(gestore, sid, "ora")

    @callback
    def _aggiorna_attributi(self) -> None:
        sv = self.sveglia
        if sv:
            hh, mm = (int(x) for x in sv.ora.split(":"))
            self._attr_native_value = time(hh, mm)
        else:
            self._attr_native_value = None

    async def async_set_value(self, value: time) -> None:
        await self._modifica(ora=f"{value.hour:02d}:{value.minute:02d}")
