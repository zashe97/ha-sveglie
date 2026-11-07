"""Logica pura delle sveglie: interpretazione di ore/giorni e calcolo della prossima suonata.

Niente import di Home Assistant qui, così si può testare da sola.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo
import re
import unicodedata

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

_GIORNI_ALIAS = {
    "lun": 0, "lunedi": 0, "lunedì": 0, "monday": 0, "mon": 0,
    "mar": 1, "martedi": 1, "tuesday": 1, "tue": 1,
    "mer": 2, "mercoledi": 2, "wednesday": 2, "wed": 2,
    "gio": 3, "giovedi": 3, "thursday": 3, "thu": 3,
    "ven": 4, "venerdi": 4, "friday": 4, "fri": 4,
    "sab": 5, "sabato": 5, "saturday": 5, "sat": 5,
    "dom": 6, "domenica": 6, "sunday": 6, "sun": 6,
}
_GRUPPI = {
    "feriali": [0, 1, 2, 3, 4],
    "giorni feriali": [0, 1, 2, 3, 4],
    "lavorativi": [0, 1, 2, 3, 4],
    "giorni lavorativi": [0, 1, 2, 3, 4],
    "dal lunedi al venerdi": [0, 1, 2, 3, 4],
    "weekdays": [0, 1, 2, 3, 4],
    "weekend": [5, 6],
    "fine settimana": [5, 6],
    "fine-settimana": [5, 6],
    "ogni giorno": [0, 1, 2, 3, 4, 5, 6],
    "tutti i giorni": [0, 1, 2, 3, 4, 5, 6],
    "sempre": [0, 1, 2, 3, 4, 5, 6],
    "giornaliera": [0, 1, 2, 3, 4, 5, 6],
    "quotidiana": [0, 1, 2, 3, 4, 5, 6],
    "daily": [0, 1, 2, 3, 4, 5, 6],
}


class ErroreSveglia(ValueError):
    """Richiesta che non si può interpretare: il messaggio va detto all'utente."""


def pulisci_nome(testo: object, massimo: int = 30) -> str | None:
    """Nome della sveglia ridotto a lettere, cifre e spazi, corto.

    Il nome torna all'agente vocale nelle frasi: tenerlo semplice impedisce di
    usarlo per infilare istruzioni nel modello.
    """
    if testo is None:
        return None
    t = "".join(c if (c.isalnum() or c == " ") else " " for c in str(testo))
    t = re.sub(r"\s+", " ", t).strip()[:massimo].strip()
    return t or None


def _norm(testo: str) -> str:
    testo = unicodedata.normalize("NFD", testo.lower())
    testo = "".join(c for c in testo if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", testo).strip()


def interpreta_ora(testo: str) -> time:
    """'8', '8:00', '08.30', '7 e 30', '19' -> time."""
    t = _norm(str(testo))
    m = re.fullmatch(r"(\d{1,2})(?:\s*(?:[:.h]|e)\s*(\d{1,2}))?", t)
    if not m:
        raise ErroreSveglia(f"Non ho capito l'ora «{testo}»: dimmela come 7:30.")
    ore = int(m.group(1))
    minuti = int(m.group(2) or 0)
    if ore == 24:
        ore = 0
    if not (0 <= ore <= 23 and 0 <= minuti <= 59):
        raise ErroreSveglia(f"L'ora «{testo}» non esiste.")
    return time(ore, minuti)


def interpreta_giorni(testo: str | list | None) -> list[int]:
    """'feriali', 'lunedì e giovedì', ['sab','dom'] -> lista di giorni (0 = lunedì)."""
    if testo is None or testo == "" or testo == []:
        return []
    if isinstance(testo, list):
        testo = ",".join(str(x) for x in testo)
    t = _norm(str(testo))
    t = re.sub(r"^(ogni|tutti i|tutte le|nel|nei|negli|il|i|di)\s+", "", t)
    if t in _GRUPPI:
        return list(_GRUPPI[t])
    if ("ogni " + t) in _GRUPPI:
        return list(_GRUPPI["ogni " + t])
    giorni: set[int] = set()
    for pezzo in re.split(r"\s*(?:,|;|/|\be\b|\bed\b|\band\b)\s*", t):
        pezzo = re.sub(r"^(ogni|il|i|di|la)\s+", "", pezzo.strip())
        if not pezzo:
            continue
        if pezzo in _GRUPPI:
            giorni.update(_GRUPPI[pezzo])
            continue
        # plurali: "lunedì" è invariabile, "sabati"/"domeniche"
        candidato = {"sabati": "sabato", "domeniche": "domenica"}.get(pezzo, pezzo)
        if candidato in _GIORNI_ALIAS:
            giorni.add(_GIORNI_ALIAS[candidato])
        else:
            raise ErroreSveglia(f"Non ho capito i giorni «{testo}».")
    return sorted(giorni)


def interpreta_quando(testo: str | None, oggi: date) -> date | None:
    """'oggi', 'domani', 'dopodomani', 'sabato', '2026-11-12', '12/11' -> data. None se vuoto."""
    if not testo:
        return None
    t = _norm(str(testo))
    t = re.sub(r"^(il|la|per|di)\s+", "", t)
    if t in ("oggi", "stasera", "stamattina", "today"):
        return oggi
    if t in ("domani", "domattina", "domani mattina", "tomorrow"):
        return oggi + timedelta(days=1)
    if t == "dopodomani":
        return oggi + timedelta(days=2)
    t_giorno = re.sub(r"\s+prossimo$|^prossimo\s+", "", t)
    if t_giorno in _GIORNI_ALIAS:
        wd = _GIORNI_ALIAS[t_giorno]
        delta = (wd - oggi.weekday()) % 7
        return oggi + timedelta(days=delta)  # stesso giorno = oggi; se l'ora è passata ci pensa prossima_suonata
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError as err:
            raise ErroreSveglia(f"La data «{testo}» non esiste.") from err
    m = re.fullmatch(r"(\d{1,2})\s*[/.\- ]\s*(\d{1,2}|[a-z]+)(?:\s*[/.\- ]\s*(\d{2,4}))?", t)
    if m:
        giorno = int(m.group(1))
        mese_txt = m.group(2)
        if mese_txt.isdigit():
            mese = int(mese_txt)
        else:
            mesi_norm = [_norm(x) for x in MESI]
            if mese_txt not in mesi_norm:
                raise ErroreSveglia(f"Non ho capito la data «{testo}».")
            mese = mesi_norm.index(mese_txt) + 1
        anno = int(m.group(3)) if m.group(3) else oggi.year
        if anno < 100:
            anno += 2000
        try:
            d = date(anno, mese, giorno)
        except ValueError as err:
            raise ErroreSveglia(f"La data «{testo}» non esiste.") from err
        if not m.group(3) and d < oggi:
            d = date(anno + 1, mese, giorno)
        return d
    raise ErroreSveglia(f"Non ho capito il giorno «{testo}».")


_UNITA = {
    "zero": 0, "un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5,
    "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10, "undici": 11, "dodici": 12,
    "tredici": 13, "quattordici": 14, "quindici": 15, "sedici": 16, "diciassette": 17,
    "diciotto": 18, "diciannove": 19,
}
_DECINE = {
    "venti": 20, "trenta": 30, "quaranta": 40, "cinquanta": 50,
    "sessanta": 60, "settanta": 70, "ottanta": 80, "novanta": 90,
}


def numero_parole(testo: str) -> int:
    """'2', 'due', 'venticinque', 'ventuno', 'cento' -> intero."""
    t = _norm(testo).replace(" ", "")
    if t.isdigit():
        return int(t)
    if t in _UNITA:
        return _UNITA[t]
    if t == "cento":
        return 100
    for parola, valore in _DECINE.items():
        for prefisso in (parola, parola[:-1]):  # "vent" + "uno", "trent" + "otto"
            if t.startswith(prefisso):
                resto = t[len(prefisso):]
                if resto == "" and prefisso == parola:
                    return valore
                if resto in _UNITA and _UNITA[resto] < 10 and resto not in ("zero", "una"):
                    return valore + _UNITA[resto]
    raise ErroreSveglia(f"Non ho capito il numero «{testo}».")


def interpreta_durata(testo: str) -> int:
    """'due minuti', '10', "un'ora e mezza", "mezz'ora", '1 ora e 5 minuti' -> minuti."""
    t = _norm(str(testo).replace("'", " ").replace("\u2019", " "))
    t = re.sub(r"\s+(per favore|grazie|prego)$", "", t).strip()
    speciali = {
        "mezz ora": 30, "mezzora": 30, "un quarto d ora": 15, "quarto d ora": 15,
        "tre quarti d ora": 45, "un ora": 60, "ora": 60,
    }
    if t in speciali:
        return speciali[t]
    m = re.fullmatch(
        r"(?:(?P<h>\S+) or[ae])?\s*(?:e\s+)?"
        r"(?:(?P<frac>mezza|mezzo|un quarto)|(?P<m>\S+)(?:\s+(?:minuti|minuto|min))?)?",
        t,
    )
    if not m or not (m.group("h") or m.group("frac") or m.group("m")):
        raise ErroreSveglia(f"Non ho capito tra quanto: «{testo}».")
    totale = 0
    if m.group("h"):
        totale += 60 * numero_parole(m.group("h"))
    if m.group("frac"):
        if not m.group("h"):
            raise ErroreSveglia(f"Non ho capito tra quanto: «{testo}».")
        totale += 30 if m.group("frac").startswith("mezz") else 15
    elif m.group("m"):
        totale += numero_parole(m.group("m"))
    return totale


def pasqua(anno: int) -> date:
    """Domenica di Pasqua (calendario gregoriano, algoritmo di Meeus/Jones/Butcher)."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese, giorno = divmod(h + l - 7 * m + 114, 31)
    return date(anno, mese, giorno + 1)


def festivi_italiani(anno: int, patrono: tuple[int, int] | None = None) -> set[date]:
    """Feste nazionali italiane dell'anno, più il patrono (giorno, mese) se dato."""
    fisse = [(1, 1), (6, 1), (25, 4), (1, 5), (2, 6), (15, 8), (1, 11), (8, 12), (25, 12), (26, 12)]
    giorni = {date(anno, m, g) for g, m in fisse}
    p = pasqua(anno)
    giorni.update({p, p + timedelta(days=1)})
    if patrono:
        try:
            giorni.add(date(anno, patrono[1], patrono[0]))
        except ValueError:
            pass
    return giorni


def interpreta_patrono(testo: str | None) -> tuple[int, int] | None:
    """'7/12', '29-06' -> (giorno, mese). Vuoto -> None."""
    if not testo or not str(testo).strip():
        return None
    m = re.fullmatch(r"\s*(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*", str(testo))
    if not m:
        raise ErroreSveglia(f"Il patrono va scritto giorno/mese, per esempio 7/12, non «{testo}».")
    g, mese = int(m.group(1)), int(m.group(2))
    try:
        date(2024, mese, g)  # anno bisestile: accetta il 29/2
    except ValueError as err:
        raise ErroreSveglia(f"La data del patrono «{testo}» non esiste.") from err
    return (g, mese)


@dataclass
class Sveglia:
    """Una sveglia."""

    id: str
    ora: str  # "HH:MM"
    device_id: str | None
    giorni: list[int] = field(default_factory=list)  # vuota = una volta sola
    data: str | None = None  # "YYYY-MM-DD", solo per quelle singole
    nome: str | None = None
    attiva: bool = True
    progressiva: bool = False  # volume che sale piano
    salta_festivi: bool = False  # solo per le ripetute
    durata: int | None = None  # minuti di suonata; None = quella generale
    salta: str | None = None  # "YYYY-MM-DD": data della prossima suonata da saltare
    posticipata: bool = False
    prossima: str | None = None  # ISO con fuso, calcolata, non salvata nella configurazione

    @property
    def ripetuta(self) -> bool:
        return bool(self.giorni)

    def to_dict(self) -> dict:
        return asdict(self)

    def configurazione(self) -> dict:
        """I campi che definiscono la sveglia (senza quelli calcolati)."""
        d = asdict(self)
        d.pop("prossima")
        d.pop("id")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Sveglia:
        campi = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        if "giorni" in campi:
            campi["giorni"] = sorted({int(x) for x in campi["giorni"] or []})
        return cls(**campi)


def prossima_suonata(
    sv: Sveglia,
    dopo: datetime,
    tz: tzinfo,
    patrono: tuple[int, int] | None = None,
    ignora_spenta: bool = False,
) -> datetime | None:
    """Prima suonata strettamente dopo `dopo`.

    None se la sveglia è spenta, o se una sveglia singola è già passata (o saltata).
    Salta la data in `salta` e, per le ripetute con salta_festivi, le feste italiane.
    """
    if not sv.attiva and not ignora_spenta:
        return None
    hh, mm = (int(x) for x in sv.ora.split(":"))
    ora = time(hh, mm)
    locale = dopo.astimezone(tz)
    salta = date.fromisoformat(sv.salta) if sv.salta else None
    if sv.giorni:
        feste: dict[int, set[date]] = {}
        for delta in range(0, 400):
            g = locale.date() + timedelta(days=delta)
            if g.weekday() not in sv.giorni or g == salta:
                continue
            if sv.salta_festivi:
                if g.year not in feste:
                    feste[g.year] = festivi_italiani(g.year, patrono)
                if g in feste[g.year]:
                    continue
            candidato = datetime.combine(g, ora, tzinfo=tz)
            if candidato > locale:
                return candidato
        return None
    if sv.data:
        giorno = date.fromisoformat(sv.data)
        if giorno == salta:
            return None
        candidato = datetime.combine(giorno, ora, tzinfo=tz)
        return candidato if candidato > locale else None
    # nessuna data: la prossima volta che sono quell'ora (come Alexa)
    candidato = datetime.combine(locale.date(), ora, tzinfo=tz)
    if candidato <= locale:
        candidato = datetime.combine(locale.date() + timedelta(days=1), ora, tzinfo=tz)
    return None if candidato.date() == salta else candidato


def risolvi_data_singola(ora: time, quando: str | None, adesso: datetime, tz: tzinfo) -> datetime:
    """Data e ora di una sveglia singola, come farebbe Alexa.

    Senza giorno: la prossima volta che arriva quell'ora (stasera -> domattina).
    Con un giorno della settimana già passato oggi: quello della settimana prossima.
    Con una data esplicita già passata: errore.
    """
    locale = adesso.astimezone(tz)
    giorno = interpreta_quando(quando, locale.date())
    if giorno is None:
        candidato = datetime.combine(locale.date(), ora, tzinfo=tz)
        if candidato <= locale:
            candidato = datetime.combine(locale.date() + timedelta(days=1), ora, tzinfo=tz)
        return candidato
    candidato = datetime.combine(giorno, ora, tzinfo=tz)
    if candidato <= locale:
        t = re.sub(r"^(il|la|per|di)\s+|\s+prossimo$|^prossimo\s+", "", _norm(str(quando)))
        if t in _GIORNI_ALIAS:
            return datetime.combine(giorno + timedelta(days=7), ora, tzinfo=tz)
        raise ErroreSveglia("Quell'orario è già passato.")
    return candidato


def descrivi_giorni(giorni: list[int]) -> str:
    g = sorted(set(giorni))
    if g == list(range(7)):
        return "ogni giorno"
    if g == [0, 1, 2, 3, 4]:
        return "dal lunedì al venerdì"
    if g == [5, 6]:
        return "nel fine settimana"
    nomi = [GIORNI[i] for i in g]
    if len(nomi) == 1:
        return "ogni " + nomi[0]
    return "ogni " + ", ".join(nomi[:-1]) + " e " + nomi[-1]


def descrivi_quando(quando: datetime, adesso: datetime) -> str:
    """'oggi alle 8:00', 'domani alle 7:30', 'sabato 15 novembre alle 9:00'."""
    q = quando.astimezone(adesso.tzinfo)
    ora = f"{q.hour}:{q.minute:02d}"
    alle = "all'" if q.hour == 1 else "alle "
    giorni = (q.date() - adesso.date()).days
    if giorni == 0:
        return f"oggi {alle}{ora}"
    if giorni == 1:
        return f"domani {alle}{ora}"
    if giorni == 2:
        return f"dopodomani {alle}{ora}"
    return f"{GIORNI[q.weekday()]} {q.day} {MESI[q.month - 1]} {alle}{ora}"


def descrivi(sv: Sveglia, adesso: datetime, tz: tzinfo) -> str:
    """Frase parlabile per una sveglia."""
    hh, mm = (int(x) for x in sv.ora.split(":"))
    alle = "all'" if hh == 1 else "alle "
    nome = f" «{sv.nome}»" if sv.nome else ""
    if sv.ripetuta:
        testo = f"sveglia{nome} {descrivi_giorni(sv.giorni)} {alle}{hh}:{mm:02d}"
    elif sv.prossima:
        testo = f"sveglia{nome} {descrivi_quando(datetime.fromisoformat(sv.prossima), adesso)}"
    else:
        testo = f"sveglia{nome} {alle}{hh}:{mm:02d}"
    if sv.posticipata:
        testo += " (posticipata)"
    if not sv.attiva:
        testo += " (spenta)"
    elif sv.salta:
        testo += " (salta la prossima)"
    return testo
