# Sveglie per Home Assistant

Sveglie in stile Alexa per i satelliti di Home Assistant (Echo con hassmic, Voice PE, ESPHome).
Si impostano **a voce** (con un agente LLM che usa l'API **Assist**) oppure **dall'interfaccia**, senza YAML,
helper o automazioni.

## A voce

- *"Sveglia alle 8"*: se le 8 di oggi sono passate la mette a domani, come Alexa.
- *"Svegliami domani alle 6:30"*, *"sabato alle 9"*, *"il 12 novembre alle 7"*.
- *"Svegliami tra 20 minuti"*, *"sveglia tra mezz'ora"*: riconosciuta in locale, senza LLM (le frasi di HA la
  scambierebbero per un comando ritardato).
- Ripetute: *"nei giorni feriali alle 7"*, *"nel weekend alle 9"*, *"ogni lunedì e giovedì alle 8"*,
  *"…tranne i festivi"*.
- *"Che sveglie ho?"* (tutte, e con più satelliti dice dove suona ognuna), *"cancella la sveglia delle 7"*, *"cancella tutte le sveglie"*.
- *"Disattiva la sveglia delle 7"* / *"riattivala"*, *"domani non svegliarmi"* (salta solo la prossima),
  *"sposta la sveglia delle 7 alle 7:30"*, *"metti il volume progressivo alla sveglia delle 7"*.
- *"Posticipa"* / *"ancora 5 minuti"* (predefinito 9 minuti), *"Alexa, stop"*.

## La scheda Sveglie

Come l'app Sveglia del telefono: in alto **Salta la prossima**, sotto l'elenco con l'ora grande, il nome, i
giorni, dove suona e l'interruttore; **+** per aggiungerne una, tocca una sveglia per modificarla o eliminarla.
Nella finestra: ora, giorni (L M M G V S D, nessuno = una volta sola), nome, *Suona su*, volume graduale,
salta i festivi, durata.

Si carica da sola con l'integrazione: in una dashboard *Aggiungi scheda* → cerca **Sveglie**, oppure in YAML
`type: custom:sveglie-card` (opzionale `title:`). La possono usare tutti gli utenti di Home Assistant.

## Dall'interfaccia

Impostazioni → Dispositivi e servizi → **Sveglie** → **Aggiungi sveglia**: ora, giorni (nessuno = una volta
sola), data, nome, dispositivo, volume progressivo, salta i festivi, durata. Ogni sveglia si modifica dallo
stesso posto (⋮ → Modifica).

Per ogni satellite vocale (Echo con hassmic, Voice PE, ESPHome) c'è un dispositivo **Sveglie <nome>** con
dentro tutte e sole le sue sveglie, anche quando non ne ha. Ogni sveglia ha:

| Entità | |
| --- | --- |
| *07:00 …* accesa | spegnere senza cancellare |
| *07:00 …* ora | cambiare l'ora |
| *07:00 …* salta la prossima | salta una volta (si spegne da sola dopo) |
| *07:00 …* volume progressivo | parte basso e sale |
| *07:00 …* salta i festivi | feste nazionali italiane e patrono |
| *07:00 …* prossima suonata | quando suonerà |

Se sposti una sveglia su un altro satellite, le sue entità passano da sole nel gruppo giusto.

Sulla **pagina del satellite stesso** (per esempio l'Echo) compaiono solo due entità di sola lettura:
**Prossima sveglia** (con l'elenco negli attributi) e il calendario **Sveglie**, con tutte le suonate
previste (spente e festivi saltati non compaiono). Nel dispositivo **Sveglie** ci sono le stesse due viste per
tutta la casa; il calendario va bene nella scheda *Calendario* della dashboard.

## Come suona

- Sul dispositivo da cui l'hai chiesta, con il suono, la luce e lo *"stop"* nativi del dispositivo (usa il
  sistema timer di Home Assistant). Su un Echo con hassmic il suono si sceglie dalla sua pagina web
  (*Timer sound*: anche il tono sveglia di Alexa) e vale per tutti i timer di quell'Echo.
- Se nessuno la ferma smette dopo la **durata** scelta (10 minuti di default): l'integrazione rilancia la
  suonata finché serve. Sull'Echo lascia *"Timers ring for"* ad almeno 1 minuto.
- **Piano B sul telefono**: se all'ora della sveglia l'Echo è scollegato o non comincia a squillare entro
  15 secondi, la sveglia suona sui *telefoni di riserva* scelti nelle opzioni (app Home Assistant): una
  notifica critica ogni minuto con **Ferma** e **Posticipa**. Su iPhone serve permettere gli *avvisi
  critici* all'app. Se è spento Home Assistant stesso non suona niente: per le sveglie importanti tieni
  anche quella del telefono.
- **Volume progressivo**: dal volume iniziale al finale nel tempo di salita, poi rimette il volume di prima.
- Le sveglie sopravvivono ai riavvii; se HA era spento all'ora della sveglia e riparte entro 15 minuti, suona
  subito. Una sveglia singola, dopo aver suonato, resta nell'elenco spenta (come Alexa e iPhone):
  chiedendo di nuovo una sveglia alla stessa ora si riaccende quella invece di crearne un'altra.
  *"Che sveglie ho?"* dice solo quelle accese.

## Installazione

1. HACS → menu ⋮ → *Archivi digitali personalizzati* → aggiungi questo repository, tipo *Integrazione*.
2. Installa **Sveglie** e riavvia Home Assistant.
3. Impostazioni → Dispositivi e servizi → Aggiungi integrazione → **Sveglie**.

Requisiti: Home Assistant 2026.10 o successivo; per la voce un agente di conversazione LLM con *Assist*
selezionato in "Controlla Home Assistant".

## Opzioni generali

Dispositivo di riserva, durata della suonata, volume progressivo per le nuove sveglie, volume iniziale e
finale, tempo di salita, minuti di posticipo, patrono (giorno/mese) per i festivi, minuti di recupero dopo un
riavvio.

## Sicurezza

Nessun servizio registrato, nessuna chiamata di rete, nessun template o comando eseguito, nessuna dipendenza
esterna. La scheda è un file JavaScript dentro l'integrazione (senza librerie esterne) e usa cinque comandi del
websocket di Home Assistant (`sveglie/*`): rispondono solo a utenti già entrati in HA, controllano ogni valore
(ora, giorni, durata, nome) e fanno suonare solo su satelliti vocali. Le sveglie suonano solo sul dispositivo
indicato da Home Assistant. Le entità delle sveglie sono di categoria *configurazione*, quindi non vengono
esposte all'assistente vocale da sole.

## Test

Logica: `python3 tests/test_logic.py`. Integrazione dentro un Home Assistant vero: con Python 3.14,
`pip install homeassistant==2026.10.0 pytest-homeassistant-custom-component hassil==3.12.1
home-assistant-intents==2026.10.6 gazetteer-matcher==1.1.0`, poi `pytest`.

## Limiti noti

- Il suono è quello dei **timer** del dispositivo: uno per dispositivo, non uno per sveglia.
- Se il dispositivo non supporta i timer, la sveglia viene annunciata con la voce (o con una notifica in HA).
