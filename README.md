# Sveglie per Home Assistant

Sveglie vocali in stile Alexa per i satelliti di Home Assistant (Echo con hassmic, Voice PE, ESPHome).
Pensata per un agente vocale LLM (OpenAI, Gemini, Local OpenAI LLM…) con l'API **Assist** attiva.

## Cosa fa

- *"Sveglia alle 8"*: se le 8 di oggi sono passate la mette a domani, come Alexa.
- *"Svegliami domani alle 6:30"*, *"sabato alle 9"*, *"il 12 novembre alle 7"*.
- *"Svegliami tra 20 minuti"*, *"sveglia tra mezz'ora"*: riconosciuta in locale, senza LLM (le frasi di HA la scambierebbero per un comando ritardato).
- Ripetute: *"nei giorni feriali alle 7"*, *"nel weekend alle 9"*, *"ogni lunedì e giovedì alle 8"*.
- *"Che sveglie ho?"*, *"cancella la sveglia delle 7"*, *"cancella tutte le sveglie"*.
- *"Posticipa"* / *"ancora 5 minuti"* (predefinito 9 minuti).
- Suona **sul dispositivo da cui l'hai chiesta**, con il suono, la luce e lo *"stop"* nativi del dispositivo
  (usa il sistema timer di Home Assistant: su un Echo con hassmic il suono si sceglie in *Voice → Timer sound*).
- Le sveglie sopravvivono ai riavvii; se HA era spento all'ora della sveglia e riparte entro 15 minuti, suona subito.
- Sensore **Prossima sveglia** con l'elenco completo negli attributi, per dashboard e automazioni.

Niente helper, automazioni o YAML da scrivere.

## Installazione

1. HACS → menu ⋮ → *Archivi digitali personalizzati* → aggiungi questo repository, tipo *Integrazione*.
2. Installa **Sveglie** e riavvia Home Assistant.
3. Impostazioni → Dispositivi e servizi → Aggiungi integrazione → **Sveglie**.

Requisiti: Home Assistant 2026.10 o successivo, agente di conversazione LLM con *Assist* selezionato in
"Controlla Home Assistant". Le sveglie si impostano tramite l'LLM (non con le frasi locali di HA).

## Opzioni

- **Dispositivo di riserva**: dove suona una sveglia impostata dalla chat dell'app (che non è un satellite).
- **Minuti di posticipo**: 9 come Alexa.
- **Minuti di recupero dopo un riavvio**.

## Limiti noti

- Suono, durata della suonata e comando "stop" sono quelli dei **timer** del dispositivo.
- Se il dispositivo non supporta i timer, la sveglia viene annunciata con la voce (e una notifica in HA).
