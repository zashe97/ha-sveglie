"""Costanti dell'integrazione Sveglie."""

DOMAIN = "sveglie"
STORAGE_KEY = "sveglie.elenco"
STORAGE_VERSION = 1

SUBENTRY_SVEGLIA = "sveglia"

# opzioni generali
CONF_DISPOSITIVO_PREDEFINITO = "dispositivo_predefinito"
CONF_MINUTI_POSTICIPO = "minuti_posticipo"
CONF_RECUPERO_MINUTI = "recupero_minuti"
CONF_DURATA = "durata"
CONF_PROGRESSIVA = "progressiva"
CONF_VOLUME_INIZIALE = "volume_iniziale"
CONF_VOLUME_FINALE = "volume_finale"
CONF_SALITA_SECONDI = "salita_secondi"
CONF_PATRONO = "patrono"
CONF_TELEFONI = "telefoni_riserva"

DEFAULT_MINUTI_POSTICIPO = 9  # come Alexa
DEFAULT_RECUPERO_MINUTI = 15  # dopo un riavvio, suona se in ritardo da meno di così
DEFAULT_DURATA = 10  # minuti di suonata se nessuno la ferma
DEFAULT_PROGRESSIVA = False
DEFAULT_VOLUME_INIZIALE = 10  # %
DEFAULT_VOLUME_FINALE = 0  # % ; 0 = il volume che il dispositivo aveva prima
DEFAULT_SALITA_SECONDI = 60
# piano B: se il satellite non comincia a suonare entro questi secondi, avvisa i telefoni
CONTROLLO_SECONDI = 15
RIPETI_AVVISO_SECONDI = 60
PREFISSO_AZIONE = "SVEGLIE_"

# campi di una sveglia (dati della sottovoce)
CONF_ORA = "ora"
CONF_GIORNI = "giorni"
CONF_DATA = "data"
CONF_NOME = "nome"
CONF_DISPOSITIVO = "device_id"
CONF_ATTIVA = "attiva"
CONF_SALTA_FESTIVI = "salta_festivi"
CONF_DURATA_SVEGLIA = "durata"

# limiti di sicurezza
MAX_SVEGLIE = 30
MAX_LUNGHEZZA_NOME = 30
MAX_MINUTI_POSTICIPO = 60
MAX_DURATA = 60

# il suono nativo di hassmic dura 1 minuto di default: lo si rilancia prima che finisca
RIARMO_SECONDI = 50

SEGNALE_AGGIORNATE = "sveglie_aggiornate"
SEGNALE_NUOVE = "sveglie_nuove"
