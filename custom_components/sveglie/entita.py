"""Base delle entità di una singola sveglia (una sottovoce = un dispositivo "Sveglia ...")."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SEGNALE_AGGIORNATE, SEGNALE_NUOVE
from .logic import ErroreSveglia, Sveglia
from .manager import GestoreSveglie

from homeassistant.exceptions import HomeAssistantError


def imposta_piattaforma(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    fabbrica: Callable[[GestoreSveglie, str], Iterable[Entity]],
) -> None:
    """Crea le entità per le sveglie che ci sono e per quelle che arriveranno."""
    gestore: GestoreSveglie = hass.data[DOMAIN]

    @callback
    def _aggiungi(ids: Iterable[str]) -> None:
        for sid in ids:
            if sid in entry.subentries:
                async_add_entities(list(fabbrica(gestore, sid)), config_subentry_id=sid)

    _aggiungi(list(gestore.sveglie))
    entry.async_on_unload(async_dispatcher_connect(hass, SEGNALE_NUOVE, _aggiungi))


class EntitaSveglia(Entity):
    """Un'entità che appartiene a una sveglia."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, gestore: GestoreSveglie, sid: str, chiave: str) -> None:
        self.gestore = gestore
        self.sid = sid
        self._attr_unique_id = f"{sid}_{chiave}"
        self._attr_translation_key = chiave
        sub = gestore.entry.subentries.get(sid)
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, sid)},
            name=sub.title if sub else "Sveglia",
            manufacturer="Sveglie",
            model="Sveglia",
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    @property
    def sveglia(self) -> Sveglia | None:
        return self.gestore.sveglie.get(self.sid)

    @property
    def available(self) -> bool:
        return self.sveglia is not None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SEGNALE_AGGIORNATE, self._aggiorna)
        )
        self._aggiorna()

    @callback
    def _aggiorna(self) -> None:
        self._aggiorna_attributi()
        # il nome del dispositivo segue il titolo della sveglia
        sub = self.gestore.entry.subentries.get(self.sid)
        if sub and self.device_entry and self.device_entry.name != sub.title:
            dr.async_get(self.hass).async_update_device(self.device_entry.id, name=sub.title)
        self.async_write_ha_state()

    @callback
    def _aggiorna_attributi(self) -> None:
        """Da sovrascrivere."""

    async def _modifica(self, **campi) -> None:
        try:
            await self.gestore.async_modifica(self.sid, **campi)
        except ErroreSveglia as err:
            raise HomeAssistantError(str(err)) from err
