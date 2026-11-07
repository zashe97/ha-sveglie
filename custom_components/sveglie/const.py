"""Costanti dell'integrazione Sveglie."""

DOMAIN = "sveglie"
STORAGE_KEY = "sveglie.elenco"
STORAGE_VERSION = 1

CONF_DISPOSITIVO_PREDEFINITO = "dispositivo_predefinito"
CONF_MINUTI_POSTICIPO = "minuti_posticipo"
CONF_RECUPERO_MINUTI = "recupero_minuti"

DEFAULT_MINUTI_POSTICIPO = 9  # come Alexa
DEFAULT_RECUPERO_MINUTI = 15  # dopo un riavvio, suona se in ritardo da meno di così

SEGNALE_AGGIORNATE = "sveglie_aggiornate"
