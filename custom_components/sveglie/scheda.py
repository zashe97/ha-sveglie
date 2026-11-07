"""La scheda "Sveglie" per la dashboard: file JavaScript e comandi websocket che usa.

Sicurezza:
- i comandi rispondono solo a utenti già autenticati in Home Assistant (websocket di HA);
- ogni valore è controllato (ora, giorni, durata, lunghezza del nome) e il nome è ripulito;
- una sveglia può suonare solo su un satellite vocale vero (o sul dispositivo che già usa);
- il file della scheda è statico e fa parte dell'integrazione: nessuna risorsa esterna.
"""

from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from typing import Any

import probatio

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MAX_DURATA, SEGNALE_AGGIORNATE
from .dispositivi import nome_dispositivo, satelliti
from .logic import ErroreSveglia, Sveglia, descrivi_giorni, risolvi_data_singola
from .manager import GestoreSveglie

URL_SCHEDA = "/sveglie_scheda/sveglie-card.js"
_FATTO = f"{DOMAIN}_scheda_registrata"
_GIORNI_BREVI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

_ORA = probatio.All(str, probatio.Match(r"^([01]?\d|2[0-3]):[0-5]\d$"))
_GIORNI = probatio.All([probatio.All(int, probatio.Range(min=0, max=6))], probatio.Length(max=7))
_ID = probatio.All(str, probatio.Length(min=1, max=64))
_CAMPI = {
    probatio.Required("ora"): _ORA,
    probatio.Optional("giorni", default=[]): _GIORNI,
    probatio.Optional("nome"): probatio.Any(None, probatio.All(str, probatio.Length(max=60))),
    probatio.Required("device_id"): _ID,
    probatio.Optional("progressiva", default=False): bool,
    probatio.Optional("salta_festivi", default=False): bool,
    probatio.Optional("durata"): probatio.Any(
        None, probatio.All(int, probatio.Range(min=1, max=MAX_DURATA))
    ),
}


async def async_registra_scheda(hass: HomeAssistant, versione: str) -> None:
    """Una volta per avvio di HA: file della scheda e comandi."""
    if hass.data.get(_FATTO):
        return
    hass.data[_FATTO] = True
    cartella = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_SCHEDA, str(cartella / "sveglie-card.js"), False)]
    )
    frontend.add_extra_js_url(hass, f"{URL_SCHEDA}?v={versione}")
    for comando in (
        ws_iscriviti,
        ws_salva,
        ws_accendi,
        ws_elimina,
        ws_salta,
    ):
        websocket_api.async_register_command(hass, comando)


# ---------------------------------------------------------------- dati per la scheda


def _gestore(hass: HomeAssistant) -> GestoreSveglie:
    gestore = hass.data.get(DOMAIN)
    if not isinstance(gestore, GestoreSveglie):
        raise ErroreSveglia("Le sveglie non sono attive.")
    return gestore


def _quando(sv: Sveglia, adesso: datetime) -> str:
    if sv.ripetuta:
        return descrivi_giorni(sv.giorni)
    # spenta (per esempio una singola che ha già suonato): come l'iPhone, niente data vecchia
    riferimento = sv.prossima if not sv.attiva else sv.prossima or (
        f"{sv.data}T{sv.ora}" if sv.data else None
    )
    if not riferimento:
        return "una volta"
    g = datetime.fromisoformat(riferimento).date()
    diff = (g - adesso.date()).days
    if diff == 0:
        return "oggi"
    if diff == 1:
        return "domani"
    return f"{_GIORNI_BREVI[g.weekday()]} {g.day}/{g.month}"


@callback
def dati_scheda(hass: HomeAssistant) -> dict[str, Any]:
    gestore = _gestore(hass)
    adesso = dt_util.now()
    sveglie = []
    for sv in sorted(gestore.sveglie.values(), key=lambda s: (s.ora, s.id)):
        sveglie.append(
            {
                "id": sv.id,
                "ora": sv.ora,
                "giorni": sv.giorni,
                "data": sv.data,
                "nome": sv.nome,
                "attiva": sv.attiva,
                "progressiva": sv.progressiva,
                "salta_festivi": sv.salta_festivi,
                "durata": sv.durata or gestore.durata,
                "device_id": sv.device_id,
                "dispositivo": nome_dispositivo(hass, sv.device_id),
                "prossima": sv.prossima,
                "salta": sv.salta,
                "posticipata": sv.posticipata,
                "quando": _quando(sv, adesso),
            }
        )
    dispositivi = [
        {"id": d, "nome": nome_dispositivo(hass, d)}
        for d in satelliti(hass)
        if nome_dispositivo(hass, d)
    ]
    return {
        "sveglie": sveglie,
        "dispositivi": dispositivi,
        "durata_predefinita": gestore.durata,
        "progressiva_predefinita": gestore.progressiva_predefinita,
        "oggi": adesso.date().isoformat(),
    }


def _controlla_dispositivo(hass: HomeAssistant, device_id: str, attuale: str | None) -> None:
    if device_id != attuale and device_id not in satelliti(hass):
        raise ErroreSveglia("Quel dispositivo non può suonare una sveglia.")


# ---------------------------------------------------------------- comandi


def _errore(connection: websocket_api.ActiveConnection, msg_id: int, err: Exception) -> None:
    connection.send_error(msg_id, "non_valido", str(err))


@websocket_api.websocket_command({probatio.Required("type"): "sveglie/iscriviti"})
@callback
def ws_iscriviti(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Manda subito le sveglie e poi di nuovo a ogni cambiamento."""

    @callback
    def _manda() -> None:
        try:
            connection.send_message(websocket_api.event_message(msg["id"], dati_scheda(hass)))
        except ErroreSveglia:
            pass

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SEGNALE_AGGIORNATE, _manda
    )
    connection.send_result(msg["id"])
    _manda()


@websocket_api.websocket_command(
    {probatio.Required("type"): "sveglie/salva", probatio.Optional("sveglia"): _ID, **_CAMPI}
)
@websocket_api.async_response
async def ws_salva(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Aggiunge una sveglia (senza id) o la modifica (con id)."""
    try:
        gestore = _gestore(hass)
        giorni = sorted(set(msg.get("giorni") or []))
        if sid := msg.get("sveglia"):
            sv = gestore.sveglie.get(sid)
            if sv is None or sv.posticipata:
                raise ErroreSveglia("Non ho trovato quella sveglia.")
            _controlla_dispositivo(hass, msg["device_id"], sv.device_id)
            sv = await gestore.async_modifica(
                sid,
                ora=msg["ora"].zfill(5),
                giorni=giorni,
                nome=msg.get("nome"),
                device_id=msg["device_id"],
                progressiva=msg["progressiva"],
                salta_festivi=msg["salta_festivi"] and bool(giorni),
                durata=msg.get("durata") if msg.get("durata") != gestore.durata else None,
            )
        else:
            _controlla_dispositivo(hass, msg["device_id"], None)
            ora = msg["ora"].zfill(5)
            quando = None
            if not giorni:
                hh, mm = (int(x) for x in ora.split(":"))
                quando = risolvi_data_singola(
                    time(hh, mm), None, dt_util.now(), gestore.tz
                )
            sv = await gestore.async_aggiungi(
                ora=ora,
                device_id=msg["device_id"],
                quando=quando,
                giorni=giorni,
                nome=msg.get("nome"),
                progressiva=msg["progressiva"],
                salta_festivi=msg["salta_festivi"],
                durata=msg.get("durata") if msg.get("durata") != gestore.durata else None,
            )
    except (ErroreSveglia, ValueError) as err:
        _errore(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], {"id": sv.id})


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "sveglie/accendi",
        probatio.Required("sveglia"): _ID,
        probatio.Required("attiva"): bool,
    }
)
@websocket_api.async_response
async def ws_accendi(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    try:
        await _gestore(hass).async_modifica(msg["sveglia"], attiva=msg["attiva"])
    except ErroreSveglia as err:
        _errore(connection, msg["id"], err)
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {probatio.Required("type"): "sveglie/elimina", probatio.Required("sveglia"): _ID}
)
@websocket_api.async_response
async def ws_elimina(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    try:
        tolte = await _gestore(hass).async_elimina([msg["sveglia"]])
        if not tolte:
            raise ErroreSveglia("Non ho trovato quella sveglia.")
    except ErroreSveglia as err:
        _errore(connection, msg["id"], err)
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "sveglie/salta",
        probatio.Optional("sveglia"): _ID,
        probatio.Optional("salta", default=True): bool,
    }
)
@websocket_api.async_response
async def ws_salta(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Senza sveglia: salta la prossima che suonerà in casa. Con sveglia: quella (o annulla)."""
    try:
        gestore = _gestore(hass)
        sid = msg.get("sveglia")
        if sid is None:
            prossime = [s for s in gestore.elenco() if s.prossima and not s.posticipata]
            if not prossime:
                raise ErroreSveglia("Non c'è nessuna sveglia da saltare.")
            sid = prossime[0].id
        sv = await gestore.async_modifica(sid, salta_prossima=msg["salta"])
    except ErroreSveglia as err:
        _errore(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], {"id": sv.id, "salta": sv.salta})
