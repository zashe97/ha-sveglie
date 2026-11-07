"""Test dell'integrazione dentro Home Assistant 2026.10."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from homeassistant.components import conversation
from homeassistant.components.intent.const import TIMER_DATA
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import Context, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er, llm
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

DOMAIN = "sveglie"


@pytest.fixture
async def echo(hass: HomeAssistant):
    """Un finto Echo con hassmic: media player, 'Timer ringing', 'Stop ringing', gestore dei timer."""
    await hass.config.async_set_time_zone("Europe/Rome")
    hass.config.language = "it"
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "intent", {})
    finto = MockConfigEntry(domain="test")
    finto.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=finto.entry_id, identifiers={("test", "echo")}, name="Echo Soggiorno"
    )
    reg = er.async_get(hass)
    ids = {}
    for dominio, uid, nome in [
        ("media_player", "50:DC/0/media_player/Media Player", "Media Player"),
        ("binary_sensor", "50:DC/0/binary_sensor/Timer ringing", "Timer ringing"),
        ("button", "50:DC/0/button/Stop ringing", "Stop ringing"),
        ("assist_satellite", "50:DC/0/assist_satellite/Assist satellite", "Assist satellite"),
    ]:
        voce = reg.async_get_or_create(
            dominio, "esphome", uid, device_id=dev.id, config_entry=finto, original_name=nome
        )
        ids[dominio] = voce.entity_id
    hass.states.async_set(ids["media_player"], "idle", {"volume_level": 0.5})
    hass.states.async_set(ids["binary_sensor"], "off")
    eventi = []
    hass.data[TIMER_DATA].register_handler(dev.id, lambda tipo, timer: eventi.append((tipo, timer.name)))
    return dev, ids, eventi


async def _avvia(hass: HomeAssistant, opzioni: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=opzioni or {}, title="Sveglie")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _strumento(hass, device_id, nome, **args):
    ctx = llm.LLMContext(
        platform="test", context=Context(), language="it", assistant="conversation", device_id=device_id
    )
    api = await llm.async_get_api(hass, llm.LLM_API_ASSIST, ctx)
    assert any(t.name == nome for t in api.tools), [t.name for t in api.tools]
    risultato = await api.async_call_tool(llm.ToolInput(tool_name=nome, tool_args=args))
    await hass.async_block_till_done()
    return getattr(risultato, "data", risultato)


async def test_avvio_e_sensore(hass: HomeAssistant, echo) -> None:
    await _avvia(hass)
    st = hass.states.get("sensor.sveglie_prossima_sveglia")
    assert st is not None and st.state == "unknown"


async def test_voce_imposta_modifica_cancella(hass: HomeAssistant, echo) -> None:
    dev, _, _ = echo
    entry = await _avvia(hass)
    r = await _strumento(hass, dev.id, "sveglie__imposta", ora="07:00", ripeti="feriali")
    assert r["success"], r
    assert "dal lunedì al venerdì" in r["frase"]
    assert len(entry.subentries) == 1
    sub = next(iter(entry.subentries.values()))
    # entità della sveglia create subito
    reg = er.async_get(hass)
    proprie = [e.entity_id for e in reg.entities.values() if e.config_subentry_id == sub.subentry_id]
    domini = sorted(e.split(".")[0] for e in proprie)
    assert domini == ["sensor", "switch", "switch", "switch", "switch", "time"], proprie
    switch_attiva = next(e for e in proprie if e.endswith("accesa"))
    assert hass.states.get(switch_attiva).state == "on"

    r = await _strumento(hass, dev.id, "sveglie__modifica", ora="07:00", attiva=False)
    assert r["success"], r
    assert hass.states.get(switch_attiva).state == "off"
    assert hass.states.get("sensor.sveglie_prossima_sveglia").state == "unknown"

    r = await _strumento(hass, dev.id, "sveglie__modifica", ora="07:00", attiva=True, nuova_ora="7:30")
    assert r["success"], r
    ora = next(e for e in proprie if e.startswith("time."))
    assert hass.states.get(ora).state == "07:30:00"

    r = await _strumento(hass, dev.id, "sveglie__modifica", ora="07:30", salta_prossima=True)
    assert r["success"] and "Suonerà di nuovo" in r["frase"], r

    r = await _strumento(hass, dev.id, "sveglie__elenca")
    assert "salta la prossima" in r["frase"], r

    r = await _strumento(hass, dev.id, "sveglie__cancella", ora="07:30")
    assert r["success"], r
    await hass.async_block_till_done()
    assert len(entry.subentries) == 0
    assert not [e for e in reg.entities.values() if e.config_subentry_id == sub.subentry_id]


async def test_interfaccia_aggiungi_e_modifica(hass: HomeAssistant, echo) -> None:
    dev, _, _ = echo
    entry = await _avvia(hass)
    res = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "sveglia"), context={"source": SOURCE_USER}
    )
    assert res["type"] is FlowResultType.FORM
    res = await hass.config_entries.subentries.async_configure(
        res["flow_id"],
        {"ora": "06:45:00", "giorni": ["5", "6"], "device_id": dev.id, "progressiva": True,
         "salta_festivi": False},
    )
    assert res["type"] is FlowResultType.CREATE_ENTRY, res
    await hass.async_block_till_done()
    sub = next(iter(entry.subentries.values()))
    assert sub.data["giorni"] == [5, 6] and sub.data["progressiva"] is True
    gestore = hass.data[DOMAIN]
    assert gestore.sveglie[sub.subentry_id].prossima
    # modifica: tutti i giorni, spenta
    res = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "sveglia"),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": sub.subentry_id},
    )
    res = await hass.config_entries.subentries.async_configure(
        res["flow_id"],
        {"ora": "06:50:00", "giorni": ["0", "1", "2", "3", "4", "5", "6"], "device_id": dev.id,
         "attiva": False, "progressiva": True, "salta_festivi": True},
    )
    assert res["type"] is FlowResultType.ABORT and res["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    sv = gestore.sveglie[sub.subentry_id]
    assert sv.ora == "06:50" and not sv.attiva and sv.prossima is None and sv.salta_festivi
    # senza dispositivo e senza riserva: errore
    res = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "sveglia"), context={"source": SOURCE_USER}
    )
    res = await hass.config_entries.subentries.async_configure(res["flow_id"], {"ora": "08:00:00"})
    assert res["type"] is FlowResultType.FORM and res["errors"] == {"device_id": "dispositivo_mancante"}


async def test_frase_locale_tra_minuti(hass: HomeAssistant, echo) -> None:
    dev, _, _ = echo
    entry = await _avvia(hass)
    assert await async_setup_component(hass, "conversation", {})
    risultato = await conversation.async_converse(
        hass, "svegliami tra due minuti", None, Context(), language="it", device_id=dev.id
    )
    testo = risultato.response.speech["plain"]["speech"]
    assert testo.startswith("Ok, sveglia impostata per oggi"), testo
    assert len(entry.subentries) == 1


async def test_suona_progressiva_e_stop(hass: HomeAssistant, echo) -> None:
    dev, ids, eventi = echo
    volumi = async_mock_service(hass, "media_player", "volume_set")
    stop = async_mock_service(hass, "button", "press")
    await _avvia(hass, {"progressiva": True, "volume_iniziale": 10, "salita_secondi": 10})
    r = await _strumento(hass, dev.id, "sveglie__imposta", tra_minuti=1)
    assert r["success"], r
    gestore = hass.data[DOMAIN]
    sv = next(iter(gestore.sveglie.values()))
    assert datetime.fromisoformat(sv.prossima) > dt_util.now()
    # l'ora arriva (si chiama direttamente quello che fa il timer di HA)
    await gestore._async_suona(sv.id)
    await asyncio.sleep(0.2)
    assert eventi and eventi[0][1] == "sveglia", eventi
    assert volumi and volumi[0].data["volume_level"] == 0.1, volumi
    hass.states.async_set(ids["binary_sensor"], "on")
    await asyncio.sleep(1.5)
    # singola: dopo aver suonato sparisce
    assert not gestore.sveglie
    # posticipa a voce: ferma il suono e crea la posticipata
    r = await _strumento(hass, dev.id, "sveglie__posticipa")
    assert r["success"], r
    assert stop and stop[-1].data["entity_id"] == ids["button"]
    assert [s for s in gestore.sveglie.values() if s.posticipata]
    await asyncio.sleep(0.2)
    # il volume è tornato com'era
    assert volumi[-1].data["volume_level"] == 0.5, [c.data for c in volumi]


async def test_scade_e_ferma_poi_stop_utente(hass: HomeAssistant, echo) -> None:
    dev, ids, eventi = echo
    stop = async_mock_service(hass, "button", "press")
    volumi = async_mock_service(hass, "media_player", "volume_set")
    await _avvia(hass)
    r = await _strumento(hass, dev.id, "sveglie__imposta", ora="06:00", ripeti="ogni giorno")
    assert r["success"], r
    gestore = hass.data[DOMAIN]
    sv = next(iter(gestore.sveglie.values()))
    await gestore._async_suona(sv.id)
    # ripetuta: resta, con una prossima suonata
    assert gestore.sveglie[sv.id].prossima
    task, suonata = gestore._suonate[dev.id]
    suonata.durata = 3  # invece di 10 minuti
    hass.states.async_set(ids["binary_sensor"], "on")
    await asyncio.wait_for(task, 10)
    assert stop and stop[-1].data["entity_id"] == ids["button"]
    assert not volumi  # non progressiva e senza volume fisso: il volume non si tocca
    # seconda suonata fermata dall'utente ("Alexa stop" spegne Timer ringing)
    stop.clear()
    await gestore._async_suona(sv.id)
    task, _ = gestore._suonate[dev.id]
    hass.states.async_set(ids["binary_sensor"], "on")
    await asyncio.sleep(1.5)
    hass.states.async_set(ids["binary_sensor"], "off")
    await asyncio.wait_for(task, 5)
    assert not stop  # già fermata dall'utente: niente pulsante


async def test_riavvio_tiene_tutto(hass: HomeAssistant, echo) -> None:
    dev, _, _ = echo
    entry = await _avvia(hass)
    await _strumento(hass, dev.id, "sveglie__imposta", ora="07:15", ripeti="lunedì e giovedì")
    await _strumento(hass, dev.id, "sveglie__imposta", ora="09:00", giorno="domani")
    assert len(entry.subentries) == 2
    gestore = hass.data[DOMAIN]
    gestore.ultima_suonata[dev.id] = next(iter(gestore.sveglie.values()))
    await gestore.async_posticipa(dev.id, 5)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    nuovo = hass.data[DOMAIN]
    assert nuovo is not gestore
    assert len(nuovo.sveglie) == 3, nuovo.sveglie
    assert sum(s.posticipata for s in nuovo.sveglie.values()) == 1
    # cambiare le opzioni ricarica e applica
    hass.config_entries.async_update_entry(entry, options={"durata": 5, "patrono": "7/12"})
    await hass.async_block_till_done()
    assert hass.data[DOMAIN].durata == 5 and hass.data[DOMAIN].patrono == (7, 12)


async def test_programmata_suona_allora_giusta(hass: HomeAssistant, echo) -> None:
    dev, ids, eventi = echo
    async_mock_service(hass, "button", "press")
    entry = await _avvia(hass)
    await _strumento(hass, dev.id, "sveglie__imposta", tra_minuti=2)
    assert len(entry.subentries) == 1
    async_fire_time_changed(hass, dt_util.now() + timedelta(seconds=30))
    await hass.async_block_till_done()
    assert not eventi  # troppo presto
    async_fire_time_changed(hass, dt_util.now() + timedelta(minutes=2, seconds=5))
    await asyncio.sleep(0.2)
    assert eventi and eventi[0][1] == "sveglia", eventi
    await hass.async_block_till_done()
    assert len(entry.subentries) == 0  # singola: sparita dopo aver suonato
    gestore = hass.data[DOMAIN]
    task, _ = gestore._suonate[dev.id]
    hass.states.async_set(ids["binary_sensor"], "on")
    await asyncio.sleep(1.2)
    hass.states.async_set(ids["binary_sensor"], "off")
    await asyncio.wait_for(task, 5)


def _secondo_echo(hass: HomeAssistant):
    finto = MockConfigEntry(domain="test")
    finto.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=finto.entry_id, identifiers={("test", "camera")}, name="Echo Camera"
    )
    er.async_get(hass).async_get_or_create(
        "assist_satellite", "esphome", "AA:BB/0/assist_satellite/x", device_id=dev.id,
        config_entry=finto, original_name="Assist satellite",
    )
    return dev


async def test_gruppi_per_dispositivo(hass: HomeAssistant, echo, caplog) -> None:
    dev, _, _ = echo
    camera = _secondo_echo(hass)
    entry = await _avvia(hass)
    dreg, ereg = dr.async_get(hass), er.async_get(hass)
    # un gruppo "Sveglie <echo>" per ogni satellite, anche senza sveglie, collegato all'echo
    gruppi = {d.via_device_id: d for d in dr.async_entries_for_config_entry(dreg, entry.entry_id)
              if d.via_device_id}
    assert set(gruppi) == {dev.id, camera.id}
    assert gruppi[dev.id].name == "Sveglie Echo Soggiorno"
    # sulla pagina dell'Echo: solo prossima sveglia e calendario, di sola lettura
    sull_echo = sorted(e.domain for e in er.async_entries_for_device(ereg, dev.id)
                       if e.platform == DOMAIN)
    assert sull_echo == ["calendar", "sensor"]

    await _strumento(hass, dev.id, "sveglie__imposta", ora="07:00", ripeti="feriali")
    await _strumento(hass, camera.id, "sveglie__imposta", ora="06:30", ripeti="weekend")
    gestore = hass.data[DOMAIN]
    sid = next(s for s, sv in gestore.sveglie.items() if sv.device_id == dev.id)
    proprie = [e for e in ereg.entities.values() if e.config_subentry_id == sid]
    assert len(proprie) == 6 and {e.device_id for e in proprie} == {gruppi[dev.id].id}
    accesa = next(e for e in proprie if e.domain == "switch" and "accesa" in e.entity_id)
    assert hass.states.get(accesa.entity_id).attributes["friendly_name"].startswith(
        "Sveglie Echo Soggiorno 07:00 dal lunedì"
    )
    # il sensore sull'echo vede solo le sue
    sensore = next(e.entity_id for e in er.async_entries_for_device(ereg, dev.id)
                   if e.platform == DOMAIN and e.domain == "sensor")
    assert hass.states.get(sensore).attributes["numero"] == 1

    # calendario: una settimana = 5 feriali sull'echo, 7 in tutte
    cal_echo = next(e.entity_id for e in er.async_entries_for_device(ereg, dev.id)
                    if e.platform == DOMAIN and e.domain == "calendar")
    inizio = dt_util.start_of_local_day()
    for cal, attesi in [(cal_echo, 5), ("calendar.sveglie_calendario", 7)]:
        r = await hass.services.async_call(
            "calendar", "get_events",
            {"entity_id": cal, "start_date_time": inizio, "end_date_time": inizio + timedelta(days=7)},
            blocking=True, return_response=True,
        )
        assert len(r[cal]["events"]) == attesi, (cal, r)

    # "che sveglie ho?" le dice tutte, con dove suonano
    r = await _strumento(hass, dev.id, "sveglie__elenca")
    assert "su Echo Soggiorno" in r["frase"] and "su Echo Camera" in r["frase"], r

    # spostata da interfaccia sull'altro echo: le entità cambiano gruppo
    res = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "sveglia"), context={"source": SOURCE_RECONFIGURE, "subentry_id": sid}
    )
    res = await hass.config_entries.subentries.async_configure(
        res["flow_id"],
        {"ora": "07:00:00", "giorni": ["0", "1", "2", "3", "4"], "device_id": camera.id,
         "attiva": True, "progressiva": False, "salta_festivi": False},
    )
    await hass.async_block_till_done()
    proprie = [e for e in ereg.entities.values() if e.config_subentry_id == sid]
    assert {e.device_id for e in proprie} == {gruppi[camera.id].id}
    assert hass.states.get(sensore).attributes["numero"] == 0
    # nessun avviso di HA su dispositivi o sottovoci usati male
    assert "subentry" not in caplog.text and "deprecated" not in caplog.text, caplog.text


async def test_icona(hass: HomeAssistant) -> None:
    from homeassistant.loader import async_get_custom_components  # noqa: PLC0415

    integrazione = (await async_get_custom_components(hass))[DOMAIN]
    assert integrazione.has_branding
    assert (Path(integrazione.file_path) / "brand" / "icon.png").is_file()
