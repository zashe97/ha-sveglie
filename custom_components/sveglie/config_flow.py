"""Configurazione da interfaccia: integrazione, opzioni generali e singole sveglie."""

from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ATTIVA,
    CONF_DATA,
    CONF_DISPOSITIVO,
    CONF_DISPOSITIVO_PREDEFINITO,
    CONF_DURATA,
    CONF_DURATA_SVEGLIA,
    CONF_GIORNI,
    CONF_MINUTI_POSTICIPO,
    CONF_NOME,
    CONF_ORA,
    CONF_PATRONO,
    CONF_PROGRESSIVA,
    CONF_RECUPERO_MINUTI,
    CONF_SALITA_SECONDI,
    CONF_SALTA_FESTIVI,
    CONF_TELEFONI,
    CONF_VOLUME_FINALE,
    CONF_VOLUME_INIZIALE,
    DEFAULT_DURATA,
    DEFAULT_MINUTI_POSTICIPO,
    DEFAULT_PROGRESSIVA,
    DEFAULT_RECUPERO_MINUTI,
    DEFAULT_SALITA_SECONDI,
    DEFAULT_VOLUME_FINALE,
    DEFAULT_VOLUME_INIZIALE,
    DOMAIN,
    MAX_DURATA,
    MAX_LUNGHEZZA_NOME,
    MAX_SVEGLIE,
    SUBENTRY_SVEGLIA,
)
from .logic import ErroreSveglia, Sveglia, interpreta_patrono, prossima_suonata, pulisci_nome
from .manager import titolo_sveglia

_GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]


def _numero(minimo: int, massimo: int, unita: str | None = None) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimo, max=massimo, step=1, mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement=unita,
        )
    )


class SveglieConfigFlow(ConfigFlow, domain=DOMAIN):
    """Aggiunge l'integrazione con un clic."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Sveglie", data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SveglieOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_SVEGLIA: SvegliaSubentryFlow}


class SveglieOptionsFlow(OptionsFlow):
    """Opzioni generali: valgono per tutte le sveglie."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errori: dict[str, str] = {}
        if user_input is not None:
            try:
                interpreta_patrono(user_input.get(CONF_PATRONO))
            except ErroreSveglia:
                errori[CONF_PATRONO] = "patrono_non_valido"
            if not errori:
                return self.async_create_entry(data=user_input)
        o = {**self.config_entry.options, **(user_input or {})}
        # i telefoni con l'app Home Assistant (notify.mobile_app_*), per il piano B
        telefoni = sorted(
            s for s in self.hass.services.async_services_for_domain("notify")
            if s.startswith("mobile_app_")
        )
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DISPOSITIVO_PREDEFINITO,
                    description={"suggested_value": o.get(CONF_DISPOSITIVO_PREDEFINITO)},
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        entity=[selector.EntityFilterSelectorConfig(domain="assist_satellite")]
                    )
                ),
                vol.Required(
                    CONF_DURATA, default=o.get(CONF_DURATA, DEFAULT_DURATA)
                ): _numero(1, MAX_DURATA, "min"),
                vol.Required(
                    CONF_PROGRESSIVA, default=o.get(CONF_PROGRESSIVA, DEFAULT_PROGRESSIVA)
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_VOLUME_INIZIALE, default=o.get(CONF_VOLUME_INIZIALE, DEFAULT_VOLUME_INIZIALE)
                ): _numero(0, 100, "%"),
                vol.Required(
                    CONF_VOLUME_FINALE, default=o.get(CONF_VOLUME_FINALE, DEFAULT_VOLUME_FINALE)
                ): _numero(0, 100, "%"),
                vol.Required(
                    CONF_SALITA_SECONDI, default=o.get(CONF_SALITA_SECONDI, DEFAULT_SALITA_SECONDI)
                ): _numero(5, 600, "s"),
                vol.Required(
                    CONF_MINUTI_POSTICIPO,
                    default=o.get(CONF_MINUTI_POSTICIPO, DEFAULT_MINUTI_POSTICIPO),
                ): _numero(1, 60, "min"),
                vol.Optional(
                    CONF_PATRONO, description={"suggested_value": o.get(CONF_PATRONO)}
                ): selector.TextSelector(),
                vol.Required(
                    CONF_RECUPERO_MINUTI,
                    default=o.get(CONF_RECUPERO_MINUTI, DEFAULT_RECUPERO_MINUTI),
                ): _numero(0, 120, "min"),
                vol.Optional(
                    CONF_TELEFONI, default=[t for t in o.get(CONF_TELEFONI, []) if t in telefoni]
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=telefoni, multiple=True, mode=selector.SelectSelectorMode.LIST
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errori)


class SvegliaSubentryFlow(ConfigSubentryFlow):
    """Aggiunge o modifica una sveglia dall'interfaccia."""

    def _schema(self, v: dict[str, Any], modifica: bool) -> vol.Schema:
        campi: dict[Any, Any] = {
            vol.Required(CONF_ORA, default=v.get(CONF_ORA, "07:00")): selector.TimeSelector(),
            vol.Optional(CONF_GIORNI, default=[str(g) for g in v.get(CONF_GIORNI, [])]): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=str(i), label=n)
                            for i, n in enumerate(_GIORNI)
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            ),
            vol.Optional(
                CONF_DATA, description={"suggested_value": v.get(CONF_DATA)}
            ): selector.DateSelector(),
            vol.Optional(
                CONF_NOME, description={"suggested_value": v.get(CONF_NOME)}
            ): selector.TextSelector(),
            vol.Optional(
                CONF_DISPOSITIVO, description={"suggested_value": v.get(CONF_DISPOSITIVO)}
            ): selector.DeviceSelector(
                selector.DeviceSelectorConfig(
                    entity=[selector.EntityFilterSelectorConfig(domain="assist_satellite")]
                )
            ),
        }
        if modifica:
            campi[vol.Required(CONF_ATTIVA, default=v.get(CONF_ATTIVA, True))] = (
                selector.BooleanSelector()
            )
        entry = self._get_entry()
        campi[
            vol.Required(
                CONF_PROGRESSIVA,
                default=v.get(CONF_PROGRESSIVA, entry.options.get(CONF_PROGRESSIVA, DEFAULT_PROGRESSIVA)),
            )
        ] = selector.BooleanSelector()
        campi[vol.Required(CONF_SALTA_FESTIVI, default=v.get(CONF_SALTA_FESTIVI, False))] = (
            selector.BooleanSelector()
        )
        campi[
            vol.Optional(
                CONF_DURATA_SVEGLIA, description={"suggested_value": v.get(CONF_DURATA_SVEGLIA)}
            )
        ] = _numero(1, MAX_DURATA, "min")
        return vol.Schema(campi)

    def _costruisci(
        self, dati: dict[str, Any], prima: dict[str, Any] | None
    ) -> tuple[Sveglia | None, dict[str, str]]:
        entry = self._get_entry()
        errori: dict[str, str] = {}
        ora = str(dati[CONF_ORA])[:5]
        giorni = sorted({int(g) for g in dati.get(CONF_GIORNI) or []})
        dispositivo = dati.get(CONF_DISPOSITIVO) or entry.options.get(CONF_DISPOSITIVO_PREDEFINITO)
        if not dispositivo:
            errori[CONF_DISPOSITIVO] = "dispositivo_mancante"
        data = dati.get(CONF_DATA) or None
        sv = Sveglia(
            id="",
            ora=ora,
            device_id=dispositivo,
            giorni=giorni,
            data=None if giorni else (str(data) if data else None),
            nome=pulisci_nome(dati.get(CONF_NOME), MAX_LUNGHEZZA_NOME),
            attiva=bool(dati.get(CONF_ATTIVA, True)),
            progressiva=bool(dati.get(CONF_PROGRESSIVA)),
            salta_festivi=bool(dati.get(CONF_SALTA_FESTIVI)) and bool(giorni),
            durata=int(dati[CONF_DURATA_SVEGLIA]) if dati.get(CONF_DURATA_SVEGLIA) else None,
            salta=(prima or {}).get("salta"),
            numero=(prima or {}).get("numero"),
        )
        tz = dt_util.get_default_time_zone()
        try:
            patrono = interpreta_patrono(entry.options.get(CONF_PATRONO))
        except ErroreSveglia:
            patrono = None
        if not giorni and not sv.data:
            # una volta sola senza data: la prossima volta che arriva quell'ora (come Alexa)
            prossima = prossima_suonata(sv, dt_util.now(), tz, patrono, ignora_spenta=True)
            sv.data = prossima.date().isoformat() if prossima else date.today().isoformat()
        if sv.attiva and prossima_suonata(sv, dt_util.now(), tz, patrono) is None:
            errori[CONF_DATA] = "gia_passata"
        return (None if errori else sv), errori

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        entry = self._get_entry()
        if len(entry.subentries) >= MAX_SVEGLIE:
            return self.async_abort(reason="troppe")
        errori: dict[str, str] = {}
        if user_input is not None:
            sv, errori = self._costruisci(user_input, None)
            if sv is not None:
                return self.async_create_entry(title=titolo_sveglia(sv), data=sv.configurazione())
        return self.async_show_form(
            step_id="user", data_schema=self._schema(user_input or {}, False), errors=errori
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        sub = self._get_reconfigure_subentry()
        errori: dict[str, str] = {}
        if user_input is not None:
            sv, errori = self._costruisci(user_input, dict(sub.data))
            if sv is not None:
                return self.async_update_and_abort(
                    self._get_entry(), sub, title=titolo_sveglia(sv), data=sv.configurazione()
                )
        valori = {**sub.data, **(user_input or {})}
        return self.async_show_form(
            step_id="reconfigure", data_schema=self._schema(valori, True), errors=errori
        )
