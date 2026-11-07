"""Gestione delle sveglie: configurazione (sottovoci), programmazione e suonata."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime, timedelta
import logging
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util, ulid as ulid_util

from .const import (
    CONF_DISPOSITIVO_PREDEFINITO,
    CONF_DURATA,
    CONF_MINUTI_POSTICIPO,
    CONF_PATRONO,
    CONF_PROGRESSIVA,
    CONF_RECUPERO_MINUTI,
    CONF_SALITA_SECONDI,
    CONF_VOLUME_FINALE,
    CONF_VOLUME_INIZIALE,
    DEFAULT_DURATA,
    DEFAULT_MINUTI_POSTICIPO,
    DEFAULT_PROGRESSIVA,
    DEFAULT_RECUPERO_MINUTI,
    DEFAULT_SALITA_SECONDI,
    DEFAULT_VOLUME_FINALE,
    DEFAULT_VOLUME_INIZIALE,
    MAX_DURATA,
    MAX_LUNGHEZZA_NOME,
    MAX_MINUTI_POSTICIPO,
    MAX_SVEGLIE,
    SEGNALE_AGGIORNATE,
    SEGNALE_NUOVE,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUBENTRY_SVEGLIA,
)
from .dispositivi import assicura_gruppi
from .logic import (
    ErroreSveglia,
    Sveglia,
    descrivi_giorni,
    interpreta_patrono,
    prossima_suonata,
    pulisci_nome,
)
from .suonata import Suonata

_LOGGER = logging.getLogger(__name__)

_GIORNI_BREVI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def titolo_sveglia(sv: Sveglia) -> str:
    """Nome leggibile della sottovoce, per esempio 'Sveglia 07:00 dal lunedì al venerdì'."""
    base = f"{sv.nome.capitalize()} {sv.ora}" if sv.nome else f"Sveglia {sv.ora}"
    if sv.ripetuta:
        return f"{base} {descrivi_giorni(sv.giorni)}"
    if sv.data:
        g = date.fromisoformat(sv.data)
        return f"{base} {_GIORNI_BREVI[g.weekday()]} {g.day}/{g.month}"
    return base


def opzione(entry: ConfigEntry, chiave: str, predefinito: Any) -> Any:
    valore = entry.options.get(chiave)
    return predefinito if valore is None or valore == "" else valore


class GestoreSveglie:
    """Tiene le sveglie e le fa suonare all'ora giusta.

    Le sveglie stanno nelle sottovoci della configurazione (si vedono e si modificano da
    Impostazioni → Dispositivi e servizi → Sveglie). Le posticipate sono temporanee e stanno
    nello Store, insieme all'ultima ora prevista di ogni sveglia per il recupero dopo un riavvio.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.opzioni = dict(entry.options)
        self.dispositivo_predefinito = entry.options.get(CONF_DISPOSITIVO_PREDEFINITO) or None
        self.minuti_posticipo = int(opzione(entry, CONF_MINUTI_POSTICIPO, DEFAULT_MINUTI_POSTICIPO))
        self.recupero_minuti = int(opzione(entry, CONF_RECUPERO_MINUTI, DEFAULT_RECUPERO_MINUTI))
        self.durata = int(opzione(entry, CONF_DURATA, DEFAULT_DURATA))
        self.progressiva_predefinita = bool(opzione(entry, CONF_PROGRESSIVA, DEFAULT_PROGRESSIVA))
        self.volume_iniziale = int(opzione(entry, CONF_VOLUME_INIZIALE, DEFAULT_VOLUME_INIZIALE))
        self.volume_finale = int(opzione(entry, CONF_VOLUME_FINALE, DEFAULT_VOLUME_FINALE))
        self.salita_secondi = int(opzione(entry, CONF_SALITA_SECONDI, DEFAULT_SALITA_SECONDI))
        try:
            self.patrono = interpreta_patrono(entry.options.get(CONF_PATRONO))
        except ErroreSveglia:
            self.patrono = None
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.sveglie: dict[str, Sveglia] = {}
        self._previste: dict[str, str] = {}
        self._annulla: dict[str, Callable[[], None]] = {}
        self._suonate: dict[str, tuple[asyncio.Task, Suonata]] = {}
        self.ultima_suonata: dict[str, Sveglia] = {}

    @property
    def tz(self):
        return dt_util.get_default_time_zone()

    # ---------------------------------------------------------------- avvio

    async def async_carica(self) -> None:
        dati = await self._store.async_load() or {}
        # versione 0.1: le sveglie stavano nello Store -> diventano sottovoci
        for d in dati.get("sveglie", []):
            try:
                vecchia = Sveglia.from_dict(d)
            except TypeError:
                continue
            if not vecchia.posticipata and len(self.entry.subentries) < MAX_SVEGLIE:
                self._aggiungi_sottovoce(vecchia)
        self._previste = dict(dati.get("previste", {}))
        adesso = dt_util.now()
        for d in dati.get("posticipate", []):
            try:
                sv = Sveglia.from_dict(d)
            except TypeError:
                continue
            if sv.prossima and datetime.fromisoformat(sv.prossima) > adesso - timedelta(
                minutes=self.recupero_minuti
            ):
                sv.posticipata = True
                self.sveglie[sv.id] = sv
        self.sincronizza(recupero=True)
        await self._async_salva()

    @callback
    def async_scarica(self) -> None:
        for annulla in self._annulla.values():
            annulla()
        self._annulla.clear()
        for task, _ in self._suonate.values():
            task.cancel()
        self._suonate.clear()

    # ------------------------------------------------- configurazione = sottovoci

    @callback
    def sincronizza(self, recupero: bool = False) -> None:
        """Riallinea le sveglie alle sottovoci (dopo un'aggiunta o una modifica da interfaccia)."""
        adesso = dt_util.now()
        recupero_td = timedelta(minutes=self.recupero_minuti)
        presenti: set[str] = set()
        nuove: list[str] = []
        for sub in self.entry.subentries.values():
            if sub.subentry_type != SUBENTRY_SVEGLIA:
                continue
            try:
                sv = Sveglia.from_dict({**sub.data, "id": sub.subentry_id})
            except (TypeError, ValueError):
                _LOGGER.warning("Sveglia %s illeggibile, la salto", sub.title)
                continue
            presenti.add(sv.id)
            if sv.id not in self.sveglie:
                nuove.append(sv.id)
            # la data da saltare è passata: la tolgo
            if sv.salta and date.fromisoformat(sv.salta) < adesso.date():
                sv.salta = None
                self._scrivi(sv)
            prevista = self._previste.get(sv.id)
            if (
                recupero
                and sv.attiva
                and prevista
                and adesso - recupero_td <= datetime.fromisoformat(prevista) <= adesso
            ):
                _LOGGER.info("Sveglia %s persa durante il riavvio: suono adesso", sv.id)
                self.sveglie[sv.id] = sv
                self.hass.async_create_task(self._async_suona(sv.id))
                continue
            nuova = prossima_suonata(sv, adesso, self.tz, self.patrono)
            if nuova is None and not sv.ripetuta and sv.attiva and sv.data:
                # singola già passata (o saltata): resta nell'elenco, spenta, come su Alexa e iPhone
                sv.attiva = False
                sv.salta = None
                self._scrivi(sv)
            sv.prossima = nuova.isoformat() if nuova else None
            self.sveglie[sv.id] = sv
            self._programma(sv)
        for sid in [s for s, sv in self.sveglie.items() if not sv.posticipata and s not in presenti]:
            self.sveglie.pop(sid)
            if annulla := self._annulla.pop(sid, None):
                annulla()
        for sv in self.sveglie.values():
            if sv.posticipata:
                self._programma(sv)
        assicura_gruppi(self.hass, self.entry, [s.device_id for s in self.sveglie.values()])
        if nuove:
            async_dispatcher_send(self.hass, SEGNALE_NUOVE, nuove)
        async_dispatcher_send(self.hass, SEGNALE_AGGIORNATE)
        self.hass.async_create_task(self._async_salva())

    def _aggiungi_sottovoce(self, sv: Sveglia) -> str:
        sub = ConfigSubentry(
            data=MappingProxyType(sv.configurazione()),
            subentry_type=SUBENTRY_SVEGLIA,
            title=titolo_sveglia(sv),
            unique_id=None,
        )
        self.hass.config_entries.async_add_subentry(self.entry, sub)
        return sub.subentry_id

    def _scrivi(self, sv: Sveglia) -> None:
        if (sub := self.entry.subentries.get(sv.id)) is None:
            return
        self.hass.config_entries.async_update_subentry(
            self.entry, sub, data=sv.configurazione(), title=titolo_sveglia(sv)
        )

    # ------------------------------------------------------------ operazioni

    async def async_aggiungi(
        self,
        ora: str,
        device_id: str | None,
        quando: datetime | None = None,
        giorni: list[int] | None = None,
        nome: str | None = None,
        progressiva: bool | None = None,
        salta_festivi: bool = False,
        durata: int | None = None,
    ) -> Sveglia:
        device_id = device_id or self.dispositivo_predefinito
        if not device_id:
            raise ErroreSveglia(
                "Non so su quale dispositivo far suonare la sveglia: chiedimela da un satellite vocale."
            )
        giorni = sorted(set(giorni or []))
        sv = Sveglia(
            id="",
            ora=ora,
            device_id=device_id,
            giorni=giorni,
            data=quando.date().isoformat() if (quando and not giorni) else None,
            nome=pulisci_nome(nome, MAX_LUNGHEZZA_NOME),
            progressiva=self.progressiva_predefinita if progressiva is None else bool(progressiva),
            salta_festivi=bool(salta_festivi) and bool(giorni),
            durata=min(MAX_DURATA, max(1, int(durata))) if durata else None,
        )
        if prossima_suonata(sv, dt_util.now(), self.tz, self.patrono) is None:
            raise ErroreSveglia("Quell'orario è già passato.")
        for altra in self.sveglie.values():
            if (
                not altra.posticipata
                and altra.device_id == sv.device_id
                and altra.ora == sv.ora
                and altra.giorni == sv.giorni
                and altra.data == sv.data
            ):
                if not altra.attiva:
                    return await self.async_modifica(altra.id, attiva=True)
                return altra
        if not sv.ripetuta:
            # come Alexa: "sveglia alle 7" riaccende la singola delle 7 già suonata (o spenta)
            # invece di crearne un'altra uguale
            for altra in self.sveglie.values():
                if (
                    not altra.posticipata
                    and not altra.ripetuta
                    and altra.device_id == sv.device_id
                    and altra.ora == sv.ora
                    and not altra.attiva
                ):
                    altra.attiva = True
                    altra.data = sv.data
                    altra.salta = None
                    if sv.nome:
                        altra.nome = sv.nome
                    if progressiva is not None:
                        altra.progressiva = bool(progressiva)
                    if durata:
                        altra.durata = sv.durata
                    self._scrivi(altra)
                    self.sincronizza()
                    return self.sveglie[altra.id]
        if len(self.sveglie) >= MAX_SVEGLIE:
            raise ErroreSveglia(f"Hai già {MAX_SVEGLIE} sveglie: cancellane qualcuna prima.")
        sid = self._aggiungi_sottovoce(sv)
        self.sincronizza()
        return self.sveglie[sid]

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

    async def async_modifica(self, sid: str, **campi: Any) -> Sveglia:
        """Cambia una sveglia: attiva, progressiva, salta_festivi, ora, salta_prossima, durata,
        nome, giorni."""
        sv = self.sveglie.get(sid)
        if sv is None:
            raise ErroreSveglia("Non ho trovato quella sveglia.")
        if sv.posticipata:
            raise ErroreSveglia("Una sveglia posticipata si può solo cancellare.")
        if "salta_prossima" in campi:
            if campi.pop("salta_prossima"):
                prossima = prossima_suonata(sv, dt_util.now(), self.tz, self.patrono)
                if prossima is None:
                    raise ErroreSveglia("Quella sveglia non deve suonare, non c'è niente da saltare.")
                sv.salta = prossima.date().isoformat()
            else:
                sv.salta = None
        for chiave in ("attiva", "progressiva", "salta_festivi"):
            if chiave in campi and campi[chiave] is not None:
                setattr(sv, chiave, bool(campi[chiave]))
        if campi.get("ora"):
            sv.ora = campi["ora"]
            if sv.data and not sv.ripetuta:
                # una singola spostata: di nuovo la prossima volta che arriva quell'ora
                sv.data = None
                prossima = prossima_suonata(sv, dt_util.now(), self.tz, self.patrono)
                sv.data = prossima.date().isoformat() if prossima else None
        if "durata" in campi:
            sv.durata = min(MAX_DURATA, max(1, int(campi["durata"]))) if campi["durata"] else None
        if campi.get("device_id") and campi["device_id"] != sv.device_id:
            sv.device_id = campi["device_id"]
        if "nome" in campi:
            sv.nome = pulisci_nome(campi["nome"], MAX_LUNGHEZZA_NOME)
        if "giorni" in campi and campi["giorni"] is not None:
            giorni = sorted({int(g) for g in campi["giorni"] if 0 <= int(g) <= 6})
            if giorni != sv.giorni:
                sv.giorni = giorni
                sv.salta = None
                sv.data = None
                if not giorni:
                    # diventa singola: la prossima volta che arriva quell'ora
                    prossima = prossima_suonata(sv, dt_util.now(), self.tz, self.patrono, True)
                    sv.data = prossima.date().isoformat() if prossima else None
        if sv.attiva and not sv.ripetuta and sv.data and (
            prossima_suonata(sv, dt_util.now(), self.tz, self.patrono) is None
        ):
            # riaccesa una singola già passata: la prossima volta che arriva quell'ora
            sv.data = None
            prossima = prossima_suonata(sv, dt_util.now(), self.tz, self.patrono)
            sv.data = prossima.date().isoformat() if prossima else None
        self._scrivi(sv)
        self.sincronizza()
        return self.sveglie[sid]

    async def async_elimina(self, ids: list[str]) -> list[Sveglia]:
        tolte = []
        for sid in ids:
            sv = self.sveglie.get(sid)
            if sv is None:
                continue
            tolte.append(sv)
            if sv.posticipata:
                self.sveglie.pop(sid)
                if annulla := self._annulla.pop(sid, None):
                    annulla()
            elif sid in self.entry.subentries:
                self.hass.config_entries.async_remove_subentry(self.entry, sid)
        if tolte:
            self.sincronizza()
        return tolte

    def elenco(self) -> list[Sveglia]:
        return sorted(
            self.sveglie.values(),
            key=lambda s: (s.prossima is None, s.prossima or "", s.ora),
        )

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
        if len(self.sveglie) >= MAX_SVEGLIE:
            raise ErroreSveglia(f"Hai già {MAX_SVEGLIE} sveglie: cancellane qualcuna prima.")
        sv = Sveglia(
            id=ulid_util.ulid_now(),
            ora=f"{quando.hour:02d}:{quando.minute:02d}",
            device_id=device_id,
            data=quando.date().isoformat(),
            nome=base.nome,
            progressiva=False,  # chi posticipa è già sveglio: suona subito al volume pieno
            durata=base.durata,
            posticipata=True,
            prossima=quando.isoformat(),
        )
        self.sveglie[sv.id] = sv
        self._programma(sv)
        async_dispatcher_send(self.hass, SEGNALE_AGGIORNATE)
        await self._async_salva()
        return sv

    async def async_ferma_suono(self, device_id: str | None) -> bool:
        """Ferma la sveglia che suona sul dispositivo. True se ne stava suonando una."""
        if not device_id:
            return False
        if (in_corso := self._suonate.pop(device_id, None)) is not None:
            task, suonata = in_corso
            task.cancel()
            await suonata.async_ferma()
            return True
        await Suonata(self.hass, device_id, "sveglia", 1, False, 0, 0, 5).async_ferma()
        return False

    # --------------------------------------------------------------- interni

    def _programma(self, sv: Sveglia) -> None:
        if annulla := self._annulla.pop(sv.id, None):
            annulla()
        if not sv.prossima:
            return
        quando = datetime.fromisoformat(sv.prossima)
        self._previste[sv.id] = sv.prossima

        @callback
        def _scatta(_now: datetime) -> None:
            self._annulla.pop(sv.id, None)
            self.hass.async_create_task(self._async_suona(sv.id))

        self._annulla[sv.id] = async_track_point_in_time(self.hass, _scatta, quando)

    async def _async_suona(self, sid: str) -> None:
        sv = self.sveglie.get(sid)
        if sv is None or not sv.attiva or not sv.device_id:
            return
        _LOGGER.info("Suona la sveglia %s (%s) su %s", sv.id, sv.ora, sv.device_id)
        self.ultima_suonata[sv.device_id] = sv
        self._avvia_suonata(sv)
        if sv.posticipata:
            self.sveglie.pop(sv.id, None)
            async_dispatcher_send(self.hass, SEGNALE_AGGIORNATE)
        elif sv.ripetuta:
            nuova = prossima_suonata(sv, dt_util.now() + timedelta(seconds=1), self.tz, self.patrono)
            sv.prossima = nuova.isoformat() if nuova else None
            if sv.salta:
                sv.salta = None
                self._scrivi(sv)
            self._programma(sv)
            async_dispatcher_send(self.hass, SEGNALE_AGGIORNATE)
        else:
            # singola: come Alexa e iPhone, dopo aver suonato resta nell'elenco spenta
            self._previste.pop(sv.id, None)
            sv.attiva = False
            sv.prossima = None
            sv.salta = None
            self._scrivi(sv)
            async_dispatcher_send(self.hass, SEGNALE_AGGIORNATE)
        await self._async_salva()

    def _avvia_suonata(self, sv: Sveglia) -> None:
        assert sv.device_id
        if (precedente := self._suonate.pop(sv.device_id, None)) is not None:
            precedente[0].cancel()
        suonata = Suonata(
            self.hass,
            sv.device_id,
            sv.nome or "sveglia",
            sv.durata or self.durata,
            sv.progressiva,
            self.volume_iniziale,
            self.volume_finale,
            self.salita_secondi,
        )

        async def _esegui() -> None:
            try:
                await suonata.async_esegui()
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("Errore mentre suonava la sveglia %s", sv.id)
            finally:
                if (corrente := self._suonate.get(sv.device_id or "")) and corrente[1] is suonata:
                    self._suonate.pop(sv.device_id or "", None)

        task = self.hass.async_create_background_task(_esegui(), f"sveglia {sv.id}")
        self._suonate[sv.device_id] = (task, suonata)

    async def _async_salva(self) -> None:
        await self._store.async_save(
            {
                "posticipate": [s.to_dict() for s in self.sveglie.values() if s.posticipata],
                "previste": {k: v for k, v in self._previste.items() if k in self.sveglie},
            }
        )
