"""Base delle entità di una singola sveglia.

Ogni sveglia è una sottovoce della configurazione; le sue entità stanno nel dispositivo
"Sveglie <satellite>" del satellite su cui suona, insieme a quelle delle altre sveglie dello
stesso satellite.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, SEGNALE_AGGIORNATE, SEGNALE_NUOVE
from .dispositivi import assicura_gruppo
from .logic import ErroreSveglia, Sveglia
from .manager import GestoreSveglie


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


def _etichetta(gestore: GestoreSveglie, sid: str) -> str:
    """'07:00 dal lunedì al venerdì' (il dispositivo si chiama già "Sveglie ...")."""
    sub = gestore.entry.subentries.get(sid)
    titolo = sub.title if sub else "Sveglia"
    return titolo.removeprefix("Sveglia ") or titolo


class EntitaSveglia(Entity):
    """Un'entità che appartiene a una sveglia."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, gestore: GestoreSveglie, sid: str, chiave: str) -> None:
        self.gestore = gestore
        self.sid = sid
        self._attr_unique_id = f"{sid}_{chiave}"
        self._attr_translation_key = chiave
        sv = gestore.sveglie.get(sid)
        self._attr_translation_placeholders = {"sveglia": _etichetta(gestore, sid)}
        # il dispositivo "Sveglie <satellite>" esiste già (lo crea il gestore): ci si aggancia
        self.device_entry = assicura_gruppo(gestore.hass, gestore.entry, sv.device_id if sv else None)

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
        # il nome segue il titolo della sveglia
        self._attr_translation_placeholders = {"sveglia": _etichetta(self.gestore, self.sid)}
        # se la sveglia è passata a un altro satellite, l'entità cambia gruppo
        sv = self.sveglia
        if sv and self.registry_entry:
            gruppo = assicura_gruppo(self.hass, self.gestore.entry, sv.device_id)
            if gruppo and self.registry_entry.device_id != gruppo.id:
                er.async_get(self.hass).async_update_entity(self.entity_id, device_id=gruppo.id)
        self.async_write_ha_state()

    @callback
    def _aggiorna_attributi(self) -> None:
        """Da sovrascrivere."""

    async def _modifica(self, **campi) -> None:
        try:
            await self.gestore.async_modifica(self.sid, **campi)
        except ErroreSveglia as err:
            raise HomeAssistantError(str(err)) from err
