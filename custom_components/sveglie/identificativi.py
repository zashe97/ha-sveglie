"""Entity_id stabili per le entità delle sveglie.

Un entity_id non deve cambiare quando cambia l'ora della sveglia (le automazioni e le schede
lo usano). Per questo non nasce dal titolo ("13:12 ogni sabato") ma da un numero che la
sveglia riceve una volta sola, unico tra le sveglie dello stesso dispositivo:

    switch.sveglie_echo_soggiorno_sveglia_1_accesa

La prima parte segue il nome del gruppo "Sveglie <dispositivo>": se il dispositivo viene
rinominato, o la sveglia passa a un altro dispositivo, gli entity_id si riallineano da soli.
"""

from __future__ import annotations

from collections.abc import Iterable
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .dispositivi import assicura_gruppo
from .logic import Sveglia

_LOGGER = logging.getLogger(__name__)

# chiave dell'entità -> ultima parte dell'entity_id
SUFFISSI = {
    "attiva": "accesa",
    "progressiva": "volume_progressivo",
    "salta_festivi": "salta_i_festivi",
    "salta_prossima": "salta_la_prossima",
    "ora": "ora",
    "prossima_suonata": "prossima_suonata",
}


@callback
def assegna_numeri(sveglie: Iterable[Sveglia]) -> list[Sveglia]:
    """Dà un numero a chi non ce l'ha (o ce l'ha uguale a un'altra dello stesso dispositivo).

    Il più basso libero sul dispositivo; le più vecchie (id ULID) tengono il loro.
    Ritorna le sveglie cambiate, da salvare.
    """
    cambiate: list[Sveglia] = []
    usati: dict[str | None, set[int]] = {}
    da_numerare: list[Sveglia] = []
    for sv in sorted((s for s in sveglie if not s.posticipata), key=lambda s: s.id):
        presi = usati.setdefault(sv.device_id, set())
        if sv.numero and sv.numero not in presi:
            presi.add(sv.numero)
        else:
            da_numerare.append(sv)
    for sv in da_numerare:
        presi = usati.setdefault(sv.device_id, set())
        numero = 1
        while numero in presi:
            numero += 1
        presi.add(numero)
        sv.numero = numero
        cambiate.append(sv)
    return cambiate


@callback
def id_atteso(
    hass: HomeAssistant, entry: ConfigEntry, sv: Sveglia, dominio: str, chiave: str
) -> str | None:
    """L'entity_id che l'entità dovrebbe avere, None se non si può dire."""
    if not sv.numero or chiave not in SUFFISSI:
        return None
    gruppo = assicura_gruppo(hass, entry, sv.device_id)
    if gruppo is None or not (nome := gruppo.name_by_user or gruppo.name):
        return None
    return f"{dominio}.{slugify(nome)}_sveglia_{sv.numero}_{SUFFISSI[chiave]}"


@callback
def allinea_entity_id(hass: HomeAssistant, entry: ConfigEntry, sveglie: dict[str, Sveglia]) -> None:
    """Rinomina gli entity_id delle sveglie che non sono quelli attesi (se il nuovo è libero)."""
    registro = er.async_get(hass)
    for voce in er.async_entries_for_config_entry(registro, entry.entry_id):
        sid, _, chiave = (voce.unique_id or "").partition("_")
        if (sv := sveglie.get(sid)) is None:
            continue
        nuovo = id_atteso(hass, entry, sv, voce.domain, chiave)
        if nuovo is None or nuovo == voce.entity_id:
            continue
        if registro.async_is_registered(nuovo):
            _LOGGER.warning("Non rinomino %s in %s: è già usato", voce.entity_id, nuovo)
            continue
        _LOGGER.info("Rinomino %s in %s", voce.entity_id, nuovo)
        registro.async_update_entity(voce.entity_id, new_entity_id=nuovo)
