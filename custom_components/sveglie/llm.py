"""Strumenti per l'agente vocale (API Assist): imposta, elenca, cancella e posticipa sveglie."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import probatio

from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.llm import (
    LLM_API_ASSIST,
    LLMContext,
    Tool,
    ToolAnnotations,
    ToolInput,
    ToolResult,
)
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .logic import (
    GIORNI,
    MESI,
    ErroreSveglia,
    descrivi,
    descrivi_giorni,
    descrivi_quando,
    interpreta_giorni,
    interpreta_ora,
    interpreta_quando,
    risolvi_data_singola,
)
from .manager import GestoreSveglie

PROMPT = (
    "Sveglie: per impostare, elencare, cancellare o posticipare le sveglie usa SEMPRE gli strumenti "
    "sveglie__* (non i timer). Passa l'ora come la dice l'utente in formato 24 ore (\"le 8 di sera\" = 20:00, "
    "\"le 7\" di mattina = 07:00) e il giorno a parole (\"domani\", \"sabato\") senza calcolare tu le date. "
    "Se l'utente non dice il giorno non passarlo: lo strumento sceglie da solo la prossima volta che arriva "
    "quell'ora. Dopo la chiamata ripeti all'utente la frase del campo 'frase' del risultato. "
    "Se il risultato è un errore, dillo e non confermare. Adesso è {adesso}."
)


def _gestore(hass: HomeAssistant) -> GestoreSveglie | None:
    return hass.data.get(DOMAIN)


def _errore(testo: str) -> ToolResult:
    return ToolResult(data={"error": testo, "frase": testo}, error=True)


class ImpostaSveglia(Tool):
    """Imposta una sveglia sul dispositivo che sta parlando."""

    name = f"{DOMAIN}__imposta"
    title = "Imposta sveglia"
    description = (
        "Imposta una sveglia che suona sul dispositivo da cui l'utente sta parlando. "
        "Esempi: 'sveglia alle 7', 'svegliami domani alle 6:30', 'sveglia nei giorni feriali alle 7', "
        "'sveglia ogni lunedì e giovedì alle 8', 'svegliami tra 20 minuti'."
    )
    annotations = ToolAnnotations(destructive=False, open_world=False)
    integration = DOMAIN
    parameters = probatio.Schema(
        {
            probatio.Optional(
                "ora", description="Ora in formato 24 ore HH:MM, per esempio 07:30 o 20:00."
            ): str,
            probatio.Optional(
                "giorno",
                description=(
                    "Solo per una sveglia singola, se l'utente lo dice: 'oggi', 'domani', "
                    "'dopodomani', un giorno della settimana ('sabato') o una data ('12 novembre')."
                ),
            ): str,
            probatio.Optional(
                "ripeti",
                description=(
                    "Solo per sveglie ripetute: 'ogni giorno', 'feriali', 'weekend' oppure i giorni "
                    "('lunedì, mercoledì e venerdì')."
                ),
            ): str,
            probatio.Optional(
                "tra_minuti", description="Per 'svegliami tra N minuti': il numero di minuti."
            ): int,
            probatio.Optional("nome", description="Nome della sveglia, solo se l'utente lo dice."): str,
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        gestore = _gestore(hass)
        if gestore is None:
            return _errore("Le sveglie non sono attive.")
        args: dict[str, Any] = tool_input.tool_args
        adesso = dt_util.now()
        tz = gestore.tz
        try:
            if args.get("tra_minuti"):
                minuti = int(args["tra_minuti"])
                if minuti <= 0 or minuti > 24 * 60:
                    raise ErroreSveglia("Posso impostarla tra 1 minuto e 24 ore da adesso.")
                quando = (adesso + timedelta(minutes=minuti)).replace(second=0, microsecond=0)
                sv = await gestore.async_aggiungi(
                    ora=f"{quando.hour:02d}:{quando.minute:02d}",
                    device_id=llm_context.device_id,
                    quando=quando,
                    nome=args.get("nome"),
                )
            else:
                if not args.get("ora"):
                    raise ErroreSveglia("A che ora la imposto?")
                ora = interpreta_ora(args["ora"])
                giorni = interpreta_giorni(args.get("ripeti"))
                quando = None if giorni else risolvi_data_singola(ora, args.get("giorno"), adesso, tz)
                sv = await gestore.async_aggiungi(
                    ora=f"{ora.hour:02d}:{ora.minute:02d}",
                    device_id=llm_context.device_id,
                    quando=quando,
                    giorni=giorni,
                    nome=args.get("nome"),
                )
        except ErroreSveglia as err:
            return _errore(str(err))
        if sv.ripetuta:
            hh, mm = int(sv.ora[:2]), sv.ora[3:]
            alle = "all'" if hh == 1 else "alle "
            frase = f"Ok, sveglia impostata {descrivi_giorni(sv.giorni)} {alle}{hh}:{mm}."
        else:
            frase = f"Ok, sveglia impostata per {descrivi_quando(datetime.fromisoformat(sv.prossima), adesso)}."
        return ToolResult(data={"success": True, "frase": frase, "sveglia": sv.to_dict()})


class ElencaSveglie(Tool):
    """Elenca le sveglie impostate."""

    name = f"{DOMAIN}__elenca"
    title = "Elenca sveglie"
    description = "Dice quali sveglie sono impostate ('che sveglie ho?', 'a che ora suona la sveglia?')."
    annotations = ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False)
    integration = DOMAIN
    parameters = probatio.Schema({})

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        gestore = _gestore(hass)
        if gestore is None:
            return _errore("Le sveglie non sono attive.")
        adesso = dt_util.now()
        elenco = gestore.elenco()
        if not elenco:
            return ToolResult(data={"sveglie": [], "frase": "Non hai sveglie impostate."})
        descrizioni = [descrivi(s, adesso, gestore.tz) for s in elenco]
        if len(descrizioni) == 1:
            frase = f"Hai una {descrizioni[0]}."
        else:
            frase = f"Hai {len(descrizioni)} sveglie: " + "; ".join(descrizioni) + "."
        return ToolResult(
            data={
                "frase": frase,
                "sveglie": [{"id": s.id, "descrizione": d} for s, d in zip(elenco, descrizioni)],
            }
        )


class CancellaSveglia(Tool):
    """Cancella una o tutte le sveglie."""

    name = f"{DOMAIN}__cancella"
    title = "Cancella sveglia"
    description = (
        "Cancella sveglie. Indica l'ora (e se serve i giorni o il nome) della sveglia da togliere, "
        "oppure tutte=true per cancellarle tutte. Se non sai quale, chiama prima sveglie__elenca e "
        "chiedi all'utente."
    )
    annotations = ToolAnnotations(open_world=False)
    integration = DOMAIN
    parameters = probatio.Schema(
        {
            probatio.Optional("ora", description="Ora della sveglia da cancellare, HH:MM."): str,
            probatio.Optional(
                "ripeti", description="Giorni della sveglia ripetuta da cancellare, se l'utente li dice."
            ): str,
            probatio.Optional("giorno", description="Giorno della sveglia singola, se l'utente lo dice."): str,
            probatio.Optional("nome", description="Nome della sveglia."): str,
            probatio.Optional("tutte", description="true per cancellare tutte le sveglie."): bool,
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        gestore = _gestore(hass)
        if gestore is None:
            return _errore("Le sveglie non sono attive.")
        args = tool_input.tool_args
        adesso = dt_util.now()
        candidate = gestore.elenco()
        if args.get("tutte"):
            tolte = await gestore.async_elimina([s.id for s in candidate])
            n = len(tolte)
            frase = "Non c'erano sveglie." if n == 0 else (
                "Ho cancellato la sveglia." if n == 1 else f"Ho cancellato tutte le {n} sveglie."
            )
            return ToolResult(data={"success": True, "frase": frase})
        try:
            if args.get("ora"):
                ora = interpreta_ora(args["ora"])
                testo = f"{ora.hour:02d}:{ora.minute:02d}"
                candidate = [s for s in candidate if s.ora == testo]
            if args.get("ripeti"):
                giorni = interpreta_giorni(args["ripeti"])
                candidate = [s for s in candidate if s.giorni == giorni]
            if args.get("giorno"):
                g = interpreta_quando(args["giorno"], adesso.date())
                candidate = [
                    s for s in candidate if s.prossima and s.prossima[:10] == (g.isoformat() if g else "")
                ]
        except ErroreSveglia as err:
            return _errore(str(err))
        if args.get("nome"):
            nome = str(args["nome"]).lower()
            candidate = [s for s in candidate if s.nome and nome in s.nome.lower()]
        if not candidate:
            return _errore("Non ho trovato nessuna sveglia così.")
        if len(candidate) > 1:
            descr = "; ".join(descrivi(s, adesso, gestore.tz) for s in candidate)
            return ToolResult(
                data={
                    "error": "ambigua",
                    "frase": f"Ne ho trovate {len(candidate)}: {descr}. Quale cancello?",
                },
                error=True,
            )
        sv = candidate[0]
        await gestore.async_elimina([sv.id])
        return ToolResult(
            data={"success": True, "frase": f"Ho cancellato la {descrivi(sv, adesso, gestore.tz)}."}
        )


class PosticipaSveglia(Tool):
    """Posticipa (snooze) la sveglia che sta suonando o che ha appena suonato."""

    name = f"{DOMAIN}__posticipa"
    title = "Posticipa sveglia"
    description = (
        "Posticipa la sveglia che sta suonando o ha appena suonato su questo dispositivo "
        "('posticipa', 'ancora cinque minuti', 'snooze')."
    )
    annotations = ToolAnnotations(destructive=False, open_world=False)
    integration = DOMAIN
    parameters = probatio.Schema(
        {
            probatio.Optional(
                "minuti", description="Minuti di rinvio, solo se l'utente li dice (altrimenti 9)."
            ): int,
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        gestore = _gestore(hass)
        if gestore is None:
            return _errore("Le sveglie non sono attive.")
        minuti = tool_input.tool_args.get("minuti")
        try:
            sv = await gestore.async_posticipa(llm_context.device_id, int(minuti) if minuti else None)
        except ErroreSveglia as err:
            return _errore(str(err))
        return ToolResult(
            data={
                "success": True,
                "frase": f"Ok, ti risveglio alle {int(sv.ora[:2])}:{sv.ora[3:]}.",
            }
        )


def _adesso_testo() -> str:
    a = dt_util.now()
    return f"{GIORNI[a.weekday()]} {a.day} {MESI[a.month - 1]} {a.year}, ore {a.hour}:{a.minute:02d}"


@callback
def async_get_tools(hass: HomeAssistant, llm_context: LLMContext, api_id: str) -> LLMTools | None:
    """Strumenti sveglie per l'API Assist."""
    if api_id != LLM_API_ASSIST or _gestore(hass) is None:
        return None
    return LLMTools(
        tools=[ImpostaSveglia(), ElencaSveglie(), CancellaSveglia(), PosticipaSveglia()],
        prompt=PROMPT.format(adesso=_adesso_testo()),
    )
