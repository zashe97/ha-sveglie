"""Comandi websocket della scheda Sveglie (dentro Home Assistant vero)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from test_ha import _avvia, echo  # noqa: F401  (fixture)

DOMAIN = "sveglie"


async def test_scheda_completa(hass: HomeAssistant, echo, hass_ws_client) -> None:  # noqa: F811
    dev, _, _ = echo
    entry = await _avvia(hass)
    ws = await hass_ws_client(hass)

    await ws.send_json({"id": 1, "type": "sveglie/iscriviti"})
    assert (await ws.receive_json())["success"]
    dati = (await ws.receive_json())["event"]
    assert dati["sveglie"] == []
    assert dati["dispositivi"] == [{"id": dev.id, "nome": "Echo Soggiorno"}]

    # aggiungi: lun e gio alle 6:45 con volume graduale
    await ws.send_json({"id": 2, "type": "sveglie/salva", "ora": "6:45", "giorni": [3, 0],
                        "nome": "Palestra!", "device_id": dev.id, "progressiva": True, "durata": 5})
    r = await ws.receive_json()
    while r.get("type") == "event":
        r = await ws.receive_json()
    assert r["success"], r
    sid = r["result"]["id"]
    sv = hass.data[DOMAIN].sveglie[sid]
    assert (sv.ora, sv.giorni, sv.nome, sv.progressiva, sv.durata) == ("06:45", [0, 3], "Palestra", True, 5)
    assert len(entry.subentries) == 1

    # l'iscrizione riceve l'aggiornamento
    dati = hass.data[DOMAIN]
    from custom_components.sveglie.scheda import dati_scheda  # noqa: PLC0415

    d = dati_scheda(hass)
    assert d["sveglie"][0]["quando"] == "ogni lunedì e giovedì"
    assert d["sveglie"][0]["dispositivo"] == "Echo Soggiorno"

    async def comando(i, **m):
        await ws.send_json({"id": i, **m})
        while (r := await ws.receive_json()).get("id") != i or r.get("type") == "event":
            pass
        return r

    # modifica: diventa una volta sola alle 7:10
    r = await comando(3, type="sveglie/salva", sveglia=sid, ora="07:10", giorni=[], device_id=dev.id)
    assert r["success"], r
    sv = hass.data[DOMAIN].sveglie[sid]
    assert sv.giorni == [] and sv.data and sv.ora == "07:10" and not sv.progressiva

    # spegni / accendi
    r = await comando(4, type="sveglie/accendi", sveglia=sid, attiva=False)
    assert r["success"] and not hass.data[DOMAIN].sveglie[sid].attiva
    r = await comando(5, type="sveglie/accendi", sveglia=sid, attiva=True)
    assert r["success"] and hass.data[DOMAIN].sveglie[sid].attiva

    # salta la prossima (senza id = la prossima in casa) e annulla
    r = await comando(6, type="sveglie/salta")
    assert r["success"] and r["result"]["salta"], r
    r = await comando(7, type="sveglie/salta", sveglia=sid, salta=False)
    assert r["success"] and r["result"]["salta"] is None

    # dispositivo che non è un satellite: rifiutato
    altro = MockConfigEntry(domain="test")
    altro.add_to_hass(hass)
    tv = dr.async_get(hass).async_get_or_create(config_entry_id=altro.entry_id, identifiers={("t", "tv")}, name="TV")
    r = await comando(8, type="sveglie/salva", ora="08:00", device_id=tv.id)
    assert not r["success"] and "non può suonare" in r["error"]["message"]

    # valori fuori dai limiti: rifiutati dallo schema
    for i, extra in enumerate(
        [{"ora": "25:00"}, {"ora": "07:00", "giorni": [7]}, {"ora": "07:00", "durata": 0},
         {"ora": "07:00", "nome": "x" * 61}],
        start=10,
    ):
        r = await comando(i, type="sveglie/salva", device_id=dev.id, **extra)
        assert not r["success"], (extra, r)

    # elimina
    r = await comando(20, type="sveglie/elimina", sveglia=sid)
    assert r["success"] and not hass.data[DOMAIN].sveglie
    r = await comando(21, type="sveglie/elimina", sveglia=sid)
    assert not r["success"]


async def test_file_scheda(hass: HomeAssistant, echo, hass_client) -> None:  # noqa: F811
    await _avvia(hass)
    client = await hass_client()
    r = await client.get("/sveglie_scheda/sveglie-card.js")
    assert r.status == 200
    assert "customElements.define(\"sveglie-card\"" in await r.text()
    from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL  # noqa: PLC0415

    assert any(u.startswith("/sveglie_scheda/sveglie-card.js?v=") for u in hass.data[DATA_EXTRA_MODULE_URL].urls)
