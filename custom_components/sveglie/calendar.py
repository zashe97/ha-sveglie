"""Calendari di sola lettura: quando suoneranno le sveglie (per satellite e di tutta la casa)."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .dispositivi import nome_dispositivo
from .logic import Sveglia, descrivi, suonate_tra
from .manager import GestoreSveglie, titolo_sveglia
from .vista import VistaSveglie, dispositivi_con_vista

# oltre non si calcola (una sveglia giornaliera in un anno = 365 eventi)
MAX_GIORNI = 400


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    gestore: GestoreSveglie = hass.data[DOMAIN]
    async_add_entities(
        [CalendarioSveglie(gestore, None)]
        + [CalendarioSveglie(gestore, d) for d in dispositivi_con_vista(hass, gestore)]
    )


class CalendarioSveglie(VistaSveglie, CalendarEntity):
    """Ogni suonata prevista è un evento lungo quanto la suonata. Spente e festivi saltati: niente."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, gestore: GestoreSveglie, device_id: str | None) -> None:
        super().__init__(gestore, device_id, "calendario")
        self._evento: CalendarEvent | None = None

    def _evento_di(self, sv: Sveglia, inizio: datetime) -> CalendarEvent:
        dove = None if self.device_id_satellite else nome_dispositivo(self.hass, sv.device_id)
        return CalendarEvent(
            start=inizio,
            end=inizio + timedelta(minutes=sv.durata or self.gestore.durata),
            summary=titolo_sveglia(sv),
            description=descrivi(sv, dt_util.now(), self.gestore.tz),
            location=dove,
            uid=f"{sv.id}_{inizio.isoformat()}",
        )

    @property
    def event(self) -> CalendarEvent | None:
        return self._evento

    @callback
    def _aggiorna_attributi(self) -> None:
        prossime = [s for s in self.sveglie() if s.prossima]
        self._evento = (
            self._evento_di(prossime[0], datetime.fromisoformat(prossime[0].prossima))
            if prossime
            else None
        )

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        end_date = min(end_date, start_date + timedelta(days=MAX_GIORNI))
        eventi: list[CalendarEvent] = []
        for sv in self.sveglie():
            durata = timedelta(minutes=sv.durata or self.gestore.durata)
            # anche quella che sta suonando adesso (iniziata prima di start_date)
            for inizio in suonate_tra(
                sv, start_date - durata, end_date, self.gestore.tz, self.gestore.patrono
            ):
                if inizio + durata > start_date:
                    eventi.append(self._evento_di(sv, inizio))
        eventi.sort(key=lambda e: e.start)
        return eventi
