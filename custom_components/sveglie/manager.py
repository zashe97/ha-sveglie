"""Gestione delle sveglie: salvataggio, programmazione e suonata sul satellite."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util, ulid as ulid_util

from .const import (
    MAX_LUNGHEZZA_NOME,
    MAX_MINUTI_POSTICIPO,
    MAX_SVEGLIE,
    DEFAULT_MINUTI_POSTICIPO,
    DEFAULT_RECUPERO_MINUTI,
    SEGNALE_AGGIORNATE,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .logic import ErroreSveglia, Sveglia, prossima_suonata, pulisci_nome

_LOGGER = logging.getLogger(__name__)


class GestoreSveglie:
    """Tiene l'elenco delle sveglie e le fa suonare all'ora giusta."""

    def __init__(
        self,
        hass: HomeAssistant,
        dispositivo_predefinito: str | None = None,
        minuti_posticipo: int = DEFAULT_MINUTI_POSTICIPO,
        recupero_minuti: int = DEFAULT_RECUPERO_MINUTI,
    ) -> None:
        self.hass = hass
        self.dispositivo_predefinito = dispositivo_predefinito
        self.minuti_posticipo = minuti_posticipo
        self.recupero_minuti = recupero_minuti
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.sveglie: dict[str, Sveglia] = {}
        self._annulla: dict[str, Callable[[], None]] = {}
        # ultima sveglia suonata per dispositivo, per "posticipa"
        self.ultima_suonata: dict[str, Sveglia] = {}

    @property
    def tz(self):
        return dt_util.get_default_time_zone()

    # ---------------------------------------------------------------- avvio

    async def async_carica(self) -> None:
        dati = await self._store.async_load() or {}
        adesso = dt_util.now()
        recupero = timedelta(minutes=self.recupero_minuti)
        for d in dati.get("sveglie", []):
            try:
                sv = Sveglia.from_dict(d)
            except TypeError:
                _LOGGER.warning("Sveglia salvata illeggibile, la salto: %s", d)
                continue
            prevista = datetime.fromisoformat(sv.prossima) if sv.prossima else None
            if prevista and prevista <= adesso:
                if adesso - prevista <= recupero:
                    _LOGGER.info("Sveglia %s persa durante il riavvio: suono adesso", sv.id)
                    self.sveglie[sv.id] = sv
                    self.hass.async_create_task(self._async_suona(sv.id))
                    continue
                if not sv.ripetuta:
                    _LOGGER.warning("Sveglia %s scaduta mentre HA era spento: la elimino", sv.id)
                    continue
            if not sv.ripetuta and prevista and prevista > adesso:
                nuova = prevista
            else:
                nuova = prossima_suonata(sv, adesso, self.tz)
            if nuova is None:
                continue
            sv.prossima = nuova.isoformat()
            self.sveglie[sv.id] = sv
            self._programma(sv)
        await self._async_salva()

    @callback
    def async_scarica(self) -> None:
        for annulla in self._annulla.values():
            annulla()
        self._annulla.clear()

    # ------------------------------------------------------------ operazioni

    async def async_aggiungi(
        self,
        ora: str,
        device_id: str | None,
        quando: datetime | None = None,
        giorni: list[int] | None = None,
        nome: str | None = None,
        posticipata: bool = False,
    ) -> Sveglia:
        device_id = device_id or self.dispositivo_predefinito
        if not device_id:
            raise ErroreSveglia(
                "Non so su quale dispositivo far suonare la sveglia: chiedimela da un satellite vocale."
            )
        sv = Sveglia(
            id=ulid_util.ulid_now(),
            ora=ora,
            device_id=device_id,
            giorni=sorted(set(giorni or [])),
            data=quando.date().isoformat() if (quando and not giorni) else None,
            nome=pulisci_nome(nome, MAX_LUNGHEZZA_NOME),
            posticipata=posticipata,
        )
        if sv.ripetuta:
            prossima = prossima_suonata(sv, dt_util.now(), self.tz)
        else:
            prossima = quando
        if prossima is None:
            raise ErroreSveglia("Quell'orario è già passato.")
        sv.prossima = prossima.isoformat()
        # stessa ora, stessi giorni, stesso dispositivo: non duplicare
        for altra in self.sveglie.values():
            if (
                altra.device_id == sv.device_id
                and altra.prossima == sv.prossima
                and altra.giorni == sv.giorni
                and not altra.posticipata
            ):
                return altra
        if len(self.sveglie) >= MAX_SVEGLIE:
            raise ErroreSveglia(f"Hai già {MAX_SVEGLIE} sveglie: cancellane qualcuna prima.")
        self.sveglie[sv.id] = sv
        self._programma(sv)
        await self._async_salva()
        return sv

    async def async_aggiungi_tra(
        self, minuti: int, device_id: str | None, nome: str | None = None
    ) -> Sveglia:
        """Sveglia singola tra N minuti ("svegliami tra 20 minuti")."""
        if minuti <= 0 or minuti > 24 * 60:
            raise ErroreSveglia("Posso impostarla tra 1 minuto e 24 ore da adesso.")
        quando = (dt_util.now() + timedelta(minutes=minuti)).replace(second=0, microsecond=0)
        return await self.async_aggiungi(
            ora=f"{quando.hour:02d}:{quando.minute:02d}",
            device_id=device_id,
            quando=quando,
            nome=nome,
        )

    async def async_elimina(self, ids: list[str]) -> list[Sveglia]:
        tolte = []
        for sid in ids:
            if (sv := self.sveglie.pop(sid, None)) is not None:
                if annulla := self._annulla.pop(sid, None):
                    annulla()
                tolte.append(sv)
        if tolte:
            await self._async_salva()
        return tolte

    def elenco(self) -> list[Sveglia]:
        return sorted(self.sveglie.values(), key=lambda s: s.prossima or "")

    async def async_posticipa(self, device_id: str | None, minuti: int | None) -> Sveglia:
        device_id = device_id or self.dispositivo_predefinito
        base = self.ultima_suonata.get(device_id or "")
        if base is None:
            raise ErroreSveglia("Non c'è nessuna sveglia da posticipare.")
        minuti = minuti or self.minuti_posticipo
        if not 1 <= minuti <= MAX_MINUTI_POSTICIPO:
            raise ErroreSveglia(f"Posso posticipare da 1 a {MAX_MINUTI_POSTICIPO} minuti.")
        await self.async_ferma_suono(device_id)
        quando = dt_util.now().replace(second=0, microsecond=0) + timedelta(minutes=minuti)
        return await self.async_aggiungi(
            ora=f"{quando.hour:02d}:{quando.minute:02d}",
            device_id=device_id,
            quando=quando,
            nome=base.nome,
            posticipata=True,
        )

    async def async_ferma_suono(self, device_id: str | None) -> None:
        """Ferma il suono sul dispositivo (lo stop del media player ferma anche i timer che suonano)."""
        if not device_id:
            return
        ent_reg = er.async_get(self.hass)
        players = [
            e.entity_id
            for e in er.async_entries_for_device(ent_reg, device_id)
            if e.domain == "media_player"
        ]
        if players:
            await self.hass.services.async_call(
                "media_player", "media_stop", {"entity_id": players}, blocking=False
            )

    # --------------------------------------------------------------- interni

    def _programma(self, sv: Sveglia) -> None:
        if annulla := self._annulla.pop(sv.id, None):
            annulla()
        if not sv.prossima:
            return
        quando = datetime.fromisoformat(sv.prossima)

        @callback
        def _scatta(_now: datetime) -> None:
            self._annulla.pop(sv.id, None)
            self.hass.async_create_task(self._async_suona(sv.id))

        self._annulla[sv.id] = async_track_point_in_time(self.hass, _scatta, quando)

    async def _async_suona(self, sid: str) -> None:
        sv = self.sveglie.get(sid)
        if sv is None:
            return
        _LOGGER.info("Suona la sveglia %s (%s) su %s", sv.id, sv.ora, sv.device_id)
        if sv.device_id:
            self.ultima_suonata[sv.device_id] = sv
        try:
            await self._async_fai_suonare(sv)
        except Exception:  # la sveglia deve comunque essere ripianificata
            _LOGGER.exception("Errore mentre suonava la sveglia %s", sv.id)
        if sv.ripetuta:
            nuova = prossima_suonata(sv, dt_util.now() + timedelta(seconds=1), self.tz)
            sv.prossima = nuova.isoformat() if nuova else None
            sv.posticipata = False
            self._programma(sv)
        else:
            self.sveglie.pop(sv.id, None)
        await self._async_salva()

    async def _async_fai_suonare(self, sv: Sveglia) -> None:
        """Usa il timer nativo del satellite (suono, luce e 'stop' gestiti dal dispositivo)."""
        from homeassistant.components.intent.const import TIMER_DATA  # noqa: PLC0415

        gestore_timer = self.hass.data.get(TIMER_DATA)
        nome = sv.nome or "sveglia"
        if gestore_timer is not None and sv.device_id and gestore_timer.is_timer_device(sv.device_id):
            gestore_timer.start_timer(
                sv.device_id,
                None,
                None,
                1,
                self.hass.config.language,
                name=nome,
            )
            return

        # Ripiego: annuncio vocale sul satellite, se il dispositivo non gestisce i timer.
        ent_reg = er.async_get(self.hass)
        satelliti = [
            e.entity_id
            for e in er.async_entries_for_device(ent_reg, sv.device_id or "")
            if e.domain == "assist_satellite"
        ]
        adesso = dt_util.now()
        frase = f"Sveglia! Sono le {adesso.hour}:{adesso.minute:02d}."
        if satelliti:
            await self.hass.services.async_call(
                "assist_satellite", "announce", {"entity_id": satelliti, "message": frase}, blocking=False
            )
            return
        dev = dr.async_get(self.hass).async_get(sv.device_id or "")
        _LOGGER.warning(
            "La sveglia %s non può suonare: il dispositivo %s non è un satellite vocale",
            sv.id,
            dev.name_by_user or dev.name if dev else sv.device_id,
        )
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {"title": "Sveglia", "message": f"{frase} (il dispositivo non ha potuto suonare)"},
            blocking=False,
        )

    async def _async_salva(self) -> None:
        await self._store.async_save({"sveglie": [s.to_dict() for s in self.sveglie.values()]})
        async_dispatcher_send(self.hass, SEGNALE_AGGIORNATE)
