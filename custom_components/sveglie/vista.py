"""Entità di sola lettura per un satellite (o per tutta la casa): base comune."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SEGNALE_AGGIORNATE
from .dispositivi import assicura_gruppi
from .logic import Sveglia
from .manager import GestoreSveglie


@callback
def info_servizio(entry: ConfigEntry) -> dr.DeviceInfo:
    """Il dispositivo "Sveglie" che raccoglie le viste di tutta la casa."""
    return dr.DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Sveglie",
        manufacturer="Sveglie",
        entry_type=dr.DeviceEntryType.SERVICE,
    )


@callback
def dispositivi_con_vista(hass: HomeAssistant, gestore: GestoreSveglie) -> list[str]:
    """Satelliti (e dispositivi con sveglie) su cui mettere "Prossima sveglia" e il calendario."""
    return assicura_gruppi(hass, gestore.entry, [s.device_id for s in gestore.sveglie.values()])


class VistaSveglie(Entity):
    """Mostra le sveglie di un satellite (device_id) o di tutta la casa (None). Non modifica niente."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, gestore: GestoreSveglie, device_id: str | None, chiave: str) -> None:
        self.gestore = gestore
        self.device_id_satellite = device_id
        entry = gestore.entry
        if device_id is None:
            self._attr_unique_id = f"{entry.entry_id}_{chiave}"
            self._attr_translation_key = chiave
            self._attr_device_info = info_servizio(entry)
        else:
            self._attr_unique_id = f"{entry.entry_id}_{device_id}_{chiave}"
            self._attr_translation_key = f"{chiave}_dispositivo"
            # sta sulla pagina del satellite stesso (l'Echo), accanto alle sue entità
            self.device_entry = dr.async_get(gestore.hass).async_get(device_id)

    def sveglie(self) -> list[Sveglia]:
        """Le sveglie di questa vista, dalla prossima che suona."""
        elenco = self.gestore.elenco()
        if self.device_id_satellite is None:
            return elenco
        return [s for s in elenco if s.device_id == self.device_id_satellite]

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SEGNALE_AGGIORNATE, self._aggiorna)
        )
        self._aggiorna()

    @callback
    def _aggiorna(self) -> None:
        self._aggiorna_attributi()
        self.async_write_ha_state()

    @callback
    def _aggiorna_attributi(self) -> None:
        """Da sovrascrivere."""
