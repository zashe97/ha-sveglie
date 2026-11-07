"""Frasi locali: "svegliami tra 10 minuti" senza passare dall'LLM.

Le frasi locali di Home Assistant leggono "<comando> tra <durata>" come un comando
ritardato ("svegliami" eseguito tra due minuti, in silenzio). Le frasi registrate qui
sono "sentence trigger", che HA controlla prima delle sue frasi e prima dell'LLM.
"""

from __future__ import annotations

import logging

from hassil.recognize import RecognizeResult

from homeassistant.components.conversation import ConversationInput
from homeassistant.components.conversation.agent_manager import get_agent_manager
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .llm import frase_impostata
from .logic import ErroreSveglia, interpreta_durata

_LOGGER = logging.getLogger(__name__)

FRASI_TRA = [
    "(svegliami|svegliarmi|sveglio|svegliatemi) (tra|fra) {durata}",
    "[(imposta|imposto|impostami|metti|metto|mettimi|crea|creami|programma)] "
    "[una|la] sveglia (tra|fra) {durata}",
]


def _device_id(hass: HomeAssistant, user_input: ConversationInput) -> str | None:
    if user_input.satellite_id and (
        voce := er.async_get(hass).async_get(user_input.satellite_id)
    ):
        return voce.device_id
    return user_input.device_id


def async_registra_frasi(hass: HomeAssistant) -> CALLBACK_TYPE:
    """Registra le frasi locali; restituisce la funzione per toglierle."""

    async def _tra(user_input: ConversationInput, result: RecognizeResult) -> str:
        gestore = hass.data.get(DOMAIN)
        if gestore is None:
            return "Le sveglie non sono attive."
        durata = result.entities.get("durata")
        testo = str(durata.value if durata else "")
        try:
            sv = await gestore.async_aggiungi_tra(
                interpreta_durata(testo), _device_id(hass, user_input)
            )
        except ErroreSveglia as err:
            return str(err)
        _LOGGER.debug("Sveglia da frase locale «%s»: %s", user_input.text, sv.prossima)
        return frase_impostata(sv, dt_util.now())

    return get_agent_manager(hass).register_trigger(
        sentences=FRASI_TRA, trigger_callback=_tra
    )
