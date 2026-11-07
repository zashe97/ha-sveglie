"""Una sveglia che suona: suono nativo del satellite, durata e volume che sale piano."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
import time

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import RIARMO_SECONDI

_LOGGER = logging.getLogger(__name__)

PASSO_VOLUME_SECONDI = 3


@dataclass
class EntitaDispositivo:
    """Le entità del satellite che servono per suonare."""

    media_player: str | None = None
    squilla: str | None = None  # binary_sensor "Timer ringing" (hassmic)
    ferma: str | None = None  # button "Stop ringing" (hassmic)
    volume_timer: str | None = None  # number "Timer volume" (hassmic con volumi separati)
    satellite: str | None = None


def trova_entita(hass: HomeAssistant, device_id: str) -> EntitaDispositivo:
    """Cerca nel registro le entità del dispositivo, senza guardare i nomi scelti dall'utente."""
    trovate = EntitaDispositivo()
    for voce in er.async_entries_for_device(er.async_get(hass), device_id):
        if voce.disabled_by:
            continue
        # hassmic: unique_id "<mac>/0/binary_sensor/Timer ringing"; si guarda anche il nome
        # originale dato dal dispositivo (non quello che l'utente può cambiare)
        chiave = re.sub(r"[\s\-]+", "_", f"{voce.unique_id or ''}|{voce.original_name or ''}".lower())
        if voce.domain == "media_player" and trovate.media_player is None:
            trovate.media_player = voce.entity_id
        elif voce.domain == "assist_satellite" and trovate.satellite is None:
            trovate.satellite = voce.entity_id
        elif voce.domain == "binary_sensor" and "timer_ringing" in chiave:
            trovate.squilla = voce.entity_id
        elif voce.domain == "button" and "stop_ringing" in chiave:
            trovate.ferma = voce.entity_id
        elif voce.domain == "number" and "timer_volume" in chiave:
            trovate.volume_timer = voce.entity_id
    return trovate


class Suonata:
    """Fa suonare una sveglia finché qualcuno non la ferma o finché non scade."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        nome: str,
        durata_minuti: int,
        progressiva: bool,
        volume_iniziale: int,
        volume_finale: int,
        salita_secondi: int,
    ) -> None:
        self.hass = hass
        self.device_id = device_id
        self.nome = nome
        self.durata = max(1, durata_minuti) * 60
        self.progressiva = progressiva
        self.volume_iniziale = volume_iniziale / 100
        self.volume_finale = volume_finale / 100 if volume_finale else None
        self.salita = max(5, salita_secondi)
        self.entita = trova_entita(hass, device_id)
        self._volume_prima: float | None = None
        self._volume_toccato = False
        self.fermata_da_noi = False

    # ------------------------------------------------------------------ volume

    def _leggi_volume(self) -> float | None:
        if self.entita.volume_timer and (st := self.hass.states.get(self.entita.volume_timer)):
            try:
                return float(st.state) / 100
            except ValueError:
                return None
        if self.entita.media_player and (st := self.hass.states.get(self.entita.media_player)):
            vol = st.attributes.get("volume_level")
            return float(vol) if vol is not None else None
        return None

    async def _imposta_volume(self, valore: float) -> None:
        valore = min(1.0, max(0.0, valore))
        self._volume_toccato = True
        if self.entita.volume_timer:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": self.entita.volume_timer, "value": round(valore * 100)},
                blocking=True,
            )
        elif self.entita.media_player:
            await self.hass.services.async_call(
                "media_player", "volume_set",
                {"entity_id": self.entita.media_player, "volume_level": round(valore, 2)},
                blocking=True,
            )

    # ------------------------------------------------------------------ suono

    def _squilla(self) -> bool | None:
        """True/False se il satellite dice se sta suonando, None se non lo sa dire."""
        if not self.entita.squilla:
            return None
        st = self.hass.states.get(self.entita.squilla)
        if st is None or st.state not in ("on", "off"):
            return None
        return st.state == "on"

    def _avvia_suono(self) -> bool:
        from homeassistant.components.intent.const import TIMER_DATA  # noqa: PLC0415

        gestore_timer = self.hass.data.get(TIMER_DATA)
        if gestore_timer is None or not gestore_timer.is_timer_device(self.device_id):
            return False
        gestore_timer.start_timer(
            self.device_id, None, None, 1, self.hass.config.language, name=self.nome
        )
        return True

    async def async_ferma(self) -> None:
        """Ferma il suono sul dispositivo."""
        self.fermata_da_noi = True
        try:
            if self.entita.ferma:
                await self.hass.services.async_call(
                    "button", "press", {"entity_id": self.entita.ferma}, blocking=True
                )
            elif self.entita.media_player:
                await self.hass.services.async_call(
                    "media_player", "media_stop", {"entity_id": self.entita.media_player},
                    blocking=True,
                )
        except HomeAssistantError as err:
            _LOGGER.warning("Non sono riuscito a fermare il suono su %s: %s", self.device_id, err)

    async def _annuncia(self) -> None:
        """Ripiego per i satelliti senza timer: una frase."""
        if self.entita.satellite:
            await self.hass.services.async_call(
                "assist_satellite", "announce",
                {"entity_id": self.entita.satellite, "message": f"{self.nome.capitalize()}!"},
                blocking=False,
            )
            return
        await self.hass.services.async_call(
            "persistent_notification", "create",
            {"title": "Sveglia", "message": f"{self.nome.capitalize()}: il dispositivo non ha potuto suonare."},
            blocking=False,
        )

    async def async_esegui(self) -> None:
        """Suona fino a stop, scadenza o annullamento del task."""
        self._volume_prima = self._leggi_volume()
        finale = self.volume_finale if self.volume_finale is not None else self._volume_prima
        if finale is None:
            finale = 0.5
        try:
            if self.progressiva:
                await self._imposta_volume(min(self.volume_iniziale, finale))
            elif self.volume_finale is not None:
                await self._imposta_volume(finale)

            if not self._avvia_suono():
                await self._annuncia()
                return

            inizio = time.monotonic()
            ultimo_riarmo = inizio
            ultimo_volume = 0.0
            visto_suonare = False
            while (trascorsi := time.monotonic() - inizio) < self.durata:
                await asyncio.sleep(1)
                stato = self._squilla()
                if stato:
                    visto_suonare = True
                elif stato is False and visto_suonare:
                    _LOGGER.debug("Sveglia fermata sul dispositivo %s", self.device_id)
                    return
                elif stato is None and trascorsi > 60:
                    return  # il dispositivo non dice se suona: un giro solo
                if self.progressiva and time.monotonic() - ultimo_volume >= PASSO_VOLUME_SECONDI:
                    ultimo_volume = time.monotonic()
                    quota = min(1.0, trascorsi / self.salita)
                    inizio_vol = min(self.volume_iniziale, finale)
                    await self._imposta_volume(inizio_vol + (finale - inizio_vol) * quota)
                if stato and time.monotonic() - ultimo_riarmo >= RIARMO_SECONDI:
                    ultimo_riarmo = time.monotonic()
                    self._avvia_suono()
            _LOGGER.debug("Sveglia scaduta dopo %s s: la fermo", self.durata)
            await self.async_ferma()
        finally:
            if self._volume_toccato and self._volume_prima is not None:
                try:
                    await self._imposta_volume(self._volume_prima)
                except Exception:  # noqa: BLE001 - il ripristino non deve far fallire niente
                    _LOGGER.warning("Non sono riuscito a rimettere il volume di prima")
