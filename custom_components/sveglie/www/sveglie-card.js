/*
 * Scheda "Sveglie" per Home Assistant: elenco, aggiungi, modifica, salta la prossima.
 * Nessuna libreria esterna: solo il websocket di Home Assistant (comandi sveglie/*).
 * Tutto il testo viene inserito con textContent (mai come HTML).
 */

const GIORNI_LETTERE = ["L", "M", "M", "G", "V", "S", "D"];
const GIORNI_NOMI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"];
const DURATE = [1, 2, 3, 5, 10, 15, 20, 30, 45, 60];

function descriviGiorni(giorni) {
  const g = [...new Set(giorni)].sort((a, b) => a - b);
  if (g.length === 0) return "Mai";
  if (g.length === 7) return "Ogni giorno";
  if (g.join() === "0,1,2,3,4") return "Dal lunedì al venerdì";
  if (g.join() === "5,6") return "Nel fine settimana";
  const nomi = g.map((i) => GIORNI_NOMI[i]);
  if (nomi.length === 1) return "Ogni " + nomi[0];
  return "Ogni " + nomi.slice(0, -1).join(", ") + " e " + nomi[nomi.length - 1];
}

function el(tag, attrs = {}, ...figli) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const f of figli) if (f) e.append(f);
  return e;
}

function interruttore(acceso, onChange, etichetta, disabilitato = false) {
  const input = el("input", {
    type: "checkbox",
    role: "switch",
    "aria-label": etichetta,
    disabled: disabilitato,
  });
  input.checked = acceso;
  input.addEventListener("change", () => onChange(input.checked));
  input.addEventListener("click", (ev) => ev.stopPropagation());
  return el("label", { class: "interruttore", onclick: (ev) => ev.stopPropagation() }, input, el("span"));
}

const STILE = `
  :host { display: block; }
  ha-card, .scheda { overflow: hidden; }
  .scheda { background: var(--ha-card-background, var(--card-background-color, #1c1c1c));
    color: var(--primary-text-color, #fff); border-radius: var(--ha-card-border-radius, 12px);
    box-shadow: var(--ha-card-box-shadow, none); border: var(--ha-card-border-width, 1px) solid
    var(--ha-card-border-color, var(--divider-color, #333)); }
  .testata { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 4px; }
  .titolo { font-size: 1.4em; font-weight: 600; }
  .piu { background: none; border: none; color: var(--accent-color, #ff9800); font-size: 2em;
    line-height: 1; cursor: pointer; padding: 0 4px; }
  .salta { margin: 8px 16px 4px; display: flex; flex-direction: column; gap: 6px; }
  .salta button { width: 100%; text-align: left; border: none; border-radius: 10px; padding: 10px 12px;
    background: var(--secondary-background-color, #2a2a2a); color: var(--primary-text-color, #fff);
    font: inherit; cursor: pointer; display: flex; justify-content: space-between; gap: 8px; }
  .salta button .azione { color: var(--accent-color, #ff9800); white-space: nowrap; }
  .salta .piccolo { color: var(--secondary-text-color, #aaa); font-size: .9em; }
  .elenco { list-style: none; margin: 0; padding: 0 0 4px; }
  .riga { display: flex; align-items: center; justify-content: space-between; gap: 12px;
    padding: 10px 16px; border-top: 1px solid var(--divider-color, #333); cursor: pointer; }
  .riga:first-child { border-top: none; }
  .ora { font-size: 3em; font-weight: 300; line-height: 1.05; font-variant-numeric: tabular-nums; }
  .dettaglio { color: var(--secondary-text-color, #aaa); font-size: .95em; margin-top: 2px; }
  .spenta .ora, .spenta .dettaglio { opacity: .45; }
  .vuoto { padding: 16px; color: var(--secondary-text-color, #aaa); }
  .errore { margin: 8px 16px; color: var(--error-color, #f44336); }
  .interruttore { position: relative; display: inline-block; width: 51px; height: 31px; flex: none; }
  .interruttore input { opacity: 0; width: 0; height: 0; position: absolute; }
  .interruttore span { position: absolute; inset: 0; border-radius: 31px; cursor: pointer;
    background: var(--switch-unchecked-track-color, #555); transition: background .2s; }
  .interruttore span::before { content: ""; position: absolute; height: 27px; width: 27px; left: 2px; top: 2px;
    border-radius: 50%; background: #fff; transition: transform .2s; }
  .interruttore input:checked + span { background: var(--switch-checked-track-color, var(--success-color, #34c759)); }
  .interruttore input:checked + span::before { transform: translateX(20px); }
  .interruttore input:disabled + span { opacity: .4; cursor: default; }
  .interruttore input:focus-visible + span { outline: 2px solid var(--accent-color, #ff9800); outline-offset: 2px; }
  .velo { position: fixed; inset: 0; background: rgba(0,0,0,.55); display: flex; align-items: flex-end;
    justify-content: center; z-index: 10; }
  .finestra { background: var(--card-background-color, #1c1c1c); color: var(--primary-text-color, #fff);
    width: 100%; max-width: 480px; max-height: 92vh; overflow: auto; border-radius: 16px 16px 0 0;
    padding: 8px 0 16px; box-sizing: border-box; }
  @media (min-width: 600px) { .velo { align-items: center; } .finestra { border-radius: 16px; } }
  .barra { display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; }
  .barra button { background: none; border: none; color: var(--accent-color, #ff9800); font: inherit;
    font-size: 1.05em; cursor: pointer; padding: 6px; }
  .barra .salva { font-weight: 600; }
  .barra .titolo-finestra { font-weight: 600; }
  .scegli-ora { display: flex; justify-content: center; padding: 8px 16px 16px; }
  .scegli-ora input { font-size: 3em; font-weight: 300; background: var(--secondary-background-color, #2a2a2a);
    color: var(--primary-text-color, #fff); border: none; border-radius: 12px; padding: 4px 16px;
    font-family: inherit; }
  .scegli-ora input::-webkit-calendar-picker-indicator { display: none; }
  .gruppo { margin: 0 16px 12px; background: var(--secondary-background-color, #2a2a2a); border-radius: 12px; }
  .voce { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 14px;
    border-top: 1px solid var(--divider-color, #333); }
  .voce:first-child { border-top: none; }
  .voce .valore { color: var(--secondary-text-color, #aaa); text-align: right; }
  .voce input[type=text], .voce select { background: transparent; border: none; color: var(--primary-text-color, #fff);
    font: inherit; text-align: right; min-width: 0; flex: 1; }
  .voce select option { color: #000; }
  .giorni { display: flex; justify-content: space-between; gap: 4px; padding: 4px 14px 14px; }
  .giorno { width: 38px; height: 38px; border-radius: 50%; border: none; font: inherit; font-weight: 600;
    background: var(--divider-color, #444); color: var(--primary-text-color, #fff); cursor: pointer; }
  .giorno[aria-pressed=true] { background: var(--accent-color, #ff9800); color: #000; }
  .elimina { display: block; margin: 8px 16px 0; width: calc(100% - 32px); border: none; border-radius: 12px;
    padding: 12px; background: var(--secondary-background-color, #2a2a2a); color: var(--error-color, #f44336);
    font: inherit; cursor: pointer; }
  .nota { margin: -4px 16px 12px; color: var(--secondary-text-color, #aaa); font-size: .85em; }
`;

class SveglieCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._dati = null;
    this._errore = null;
    this._finestra = null;
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = config || {};
  }

  getCardSize() {
    return 2 + (this._dati ? this._dati.sveglie.length * 2 : 2);
  }

  set hass(hass) {
    const prima = this._hass;
    this._hass = hass;
    if (!prima || prima.connection !== hass.connection) this._iscriviti();
  }

  connectedCallback() {
    if (this._hass && !this._annulla) this._iscriviti();
  }

  disconnectedCallback() {
    this._smetti();
  }

  _smetti() {
    if (this._annulla) {
      this._annulla.then((f) => f && f()).catch(() => {});
      this._annulla = null;
    }
  }

  _iscriviti() {
    this._smetti();
    if (!this._hass) return;
    this._annulla = this._hass.connection
      .subscribeMessage((dati) => {
        this._dati = dati;
        this._errore = null;
        this._disegna();
      }, { type: "sveglie/iscriviti" })
      .catch((err) => {
        this._errore = "L'integrazione Sveglie non risponde: " + (err.message || err.code || err);
        this._disegna();
        return null;
      });
    this._disegna();
  }

  async _comando(messaggio) {
    try {
      const r = await this._hass.callWS(messaggio);
      this._errore = null;
      return r;
    } catch (err) {
      this._errore = err.message || String(err);
      this._disegna();
      throw err;
    }
  }

  // ------------------------------------------------------------ disegno

  _disegna() {
    const r = this.shadowRoot;
    r.replaceChildren(el("style", { text: STILE }));
    const scheda = el("div", { class: "scheda" });
    const titolo = this._config && this._config.title ? this._config.title : "Sveglie";
    scheda.append(
      el(
        "div",
        { class: "testata" },
        el("div", { class: "titolo", text: titolo }),
        el("button", {
          class: "piu",
          text: "+",
          title: "Aggiungi sveglia",
          "aria-label": "Aggiungi sveglia",
          onclick: () => this._apri(null),
        })
      )
    );
    if (this._errore) scheda.append(el("div", { class: "errore", text: this._errore }));
    if (!this._dati) {
      scheda.append(el("div", { class: "vuoto", text: "Carico le sveglie…" }));
      r.append(scheda);
      return;
    }
    scheda.append(this._parteSalta());
    const sveglie = this._dati.sveglie;
    if (sveglie.length === 0) {
      scheda.append(el("div", { class: "vuoto", text: "Nessuna sveglia. Premi + per aggiungerne una." }));
    } else {
      const lista = el("ul", { class: "elenco" });
      for (const sv of sveglie) lista.append(this._riga(sv));
      scheda.append(lista);
    }
    r.append(scheda);
    if (this._finestra) r.append(this._finestra.nodo);
  }

  _parteSalta() {
    const box = el("div", { class: "salta" });
    const prossime = this._dati.sveglie
      .filter((s) => s.prossima && !s.posticipata)
      .sort((a, b) => (a.prossima < b.prossima ? -1 : 1));
    if (prossime.length) {
      const p = prossime[0];
      const quando = this._quandoProssima(p);
      box.append(
        el(
          "button",
          { onclick: () => this._comando({ type: "sveglie/salta" }).catch(() => {}) },
          el("span", {}, document.createTextNode("Prossima: " + quando), el("br"),
            el("span", { class: "piccolo", text: p.dispositivo ? "su " + p.dispositivo : "" })),
          el("span", { class: "azione", text: "Salta" })
        )
      );
    }
    for (const s of this._dati.sveglie.filter((x) => x.salta)) {
      const [a, m, g] = s.salta.split("-").map(Number);
      const giorno = new Date(a, m - 1, g);
      const testo = `Saltata: ${s.ora} di ${GIORNI_NOMI[(giorno.getDay() + 6) % 7]} ${g}/${m}`;
      box.append(
        el(
          "button",
          { onclick: () => this._comando({ type: "sveglie/salta", sveglia: s.id, salta: false }).catch(() => {}) },
          el("span", { class: "piccolo", text: testo }),
          el("span", { class: "azione", text: "Annulla" })
        )
      );
    }
    return box;
  }

  _quandoProssima(s) {
    const d = new Date(s.prossima);
    const oggi = new Date(this._dati.oggi + "T00:00:00");
    const giorni = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - oggi) / 86400000);
    const ora = s.ora;
    if (giorni === 0) return `oggi alle ${ora}`;
    if (giorni === 1) return `domani alle ${ora}`;
    return `${GIORNI_NOMI[(d.getDay() + 6) % 7]} ${d.getDate()}/${d.getMonth() + 1} alle ${ora}`;
  }

  _riga(sv) {
    const parti = [sv.nome || "Sveglia"];
    if (sv.posticipata) parti.push("posticipata");
    else parti.push(sv.quando);
    let dettaglio = parti.join(", ");
    if (sv.dispositivo) dettaglio += " · " + sv.dispositivo;
    const riga = el(
      "li",
      {
        class: "riga" + (sv.attiva ? "" : " spenta"),
        tabindex: "0",
        role: "button",
        "aria-label": `Modifica sveglia delle ${sv.ora}`,
        onclick: () => !sv.posticipata && this._apri(sv),
        onkeydown: (ev) => {
          if ((ev.key === "Enter" || ev.key === " ") && !sv.posticipata) {
            ev.preventDefault();
            this._apri(sv);
          }
        },
      },
      el("div", {}, el("div", { class: "ora", text: sv.ora }), el("div", { class: "dettaglio", text: dettaglio })),
      interruttore(
        sv.attiva,
        (acceso) => this._comando({ type: "sveglie/accendi", sveglia: sv.id, attiva: acceso }).catch(() => {}),
        `Sveglia delle ${sv.ora} accesa`,
        sv.posticipata
      )
    );
    return riga;
  }

  // ------------------------------------------------------------ finestra aggiungi/modifica

  _apri(sv) {
    const d = this._dati;
    const dispositivi = d.dispositivi.slice();
    if (sv && sv.device_id && !dispositivi.some((x) => x.id === sv.device_id)) {
      dispositivi.push({ id: sv.device_id, nome: sv.dispositivo || "Dispositivo" });
    }
    const stato = sv
      ? {
          id: sv.id,
          ora: sv.ora,
          giorni: sv.giorni.slice(),
          nome: sv.nome || "",
          device_id: sv.device_id,
          progressiva: sv.progressiva,
          salta_festivi: sv.salta_festivi,
          durata: sv.durata,
        }
      : {
          ora: "07:00",
          giorni: [],
          nome: "",
          device_id: dispositivi.length ? dispositivi[0].id : null,
          progressiva: d.progressiva_predefinita,
          salta_festivi: false,
          durata: d.durata_predefinita,
        };

    const chiudi = () => {
      this._finestra = null;
      this._disegna();
    };
    const salva = async () => {
      if (!stato.device_id) {
        this._errore = "Non c'è nessun satellite vocale su cui far suonare la sveglia.";
        chiudi();
        return;
      }
      const msg = {
        type: "sveglie/salva",
        ora: stato.ora,
        giorni: stato.giorni,
        nome: stato.nome.trim() || null,
        device_id: stato.device_id,
        progressiva: stato.progressiva,
        salta_festivi: stato.salta_festivi && stato.giorni.length > 0,
        durata: Number(stato.durata),
      };
      if (stato.id) msg.sveglia = stato.id;
      try {
        await this._comando(msg);
        chiudi();
      } catch (e) {
        errore.textContent = this._errore;
      }
    };

    const ripeti = el("span", { class: "valore", text: descriviGiorni(stato.giorni) });
    const festivi = interruttore(stato.salta_festivi, (v) => (stato.salta_festivi = v), "Salta i festivi",
      stato.giorni.length === 0);
    const cerchi = GIORNI_LETTERE.map((lettera, i) => {
      const b = el("button", {
        class: "giorno",
        text: lettera,
        "aria-label": GIORNI_NOMI[i],
        "aria-pressed": String(stato.giorni.includes(i)),
        onclick: () => {
          const pos = stato.giorni.indexOf(i);
          if (pos >= 0) stato.giorni.splice(pos, 1);
          else stato.giorni.push(i);
          stato.giorni.sort((a, b2) => a - b2);
          b.setAttribute("aria-pressed", String(stato.giorni.includes(i)));
          ripeti.textContent = descriviGiorni(stato.giorni);
          festivi.querySelector("input").disabled = stato.giorni.length === 0;
        },
      });
      return b;
    });

    const inputOra = el("input", { type: "time", value: stato.ora, required: true, "aria-label": "Ora" });
    inputOra.addEventListener("change", () => inputOra.value && (stato.ora = inputOra.value.slice(0, 5)));
    inputOra.addEventListener("input", () => inputOra.value && (stato.ora = inputOra.value.slice(0, 5)));

    const inputNome = el("input", { type: "text", value: stato.nome, maxlength: "30", placeholder: "Sveglia",
      "aria-label": "Nome" });
    inputNome.addEventListener("input", () => (stato.nome = inputNome.value));

    const sceltaDisp = el("select", { "aria-label": "Suona su" });
    for (const x of dispositivi) {
      const o = el("option", { value: x.id, text: x.nome });
      if (x.id === stato.device_id) o.selected = true;
      sceltaDisp.append(o);
    }
    sceltaDisp.addEventListener("change", () => (stato.device_id = sceltaDisp.value));

    const sceltaDurata = el("select", { "aria-label": "Durata" });
    const durate = DURATE.includes(Number(stato.durata)) ? DURATE : [...DURATE, Number(stato.durata)].sort((a, b) => a - b);
    for (const m of durate) {
      const o = el("option", { value: String(m), text: m === 1 ? "1 minuto" : `${m} minuti` });
      if (m === Number(stato.durata)) o.selected = true;
      sceltaDurata.append(o);
    }
    sceltaDurata.addEventListener("change", () => (stato.durata = Number(sceltaDurata.value)));

    const errore = el("div", { class: "errore" });
    const finestra = el(
      "div",
      { class: "finestra", role: "dialog", "aria-modal": "true", "aria-label": sv ? "Modifica sveglia" : "Aggiungi sveglia",
        onclick: (ev) => ev.stopPropagation() },
      el(
        "div",
        { class: "barra" },
        el("button", { text: "Annulla", onclick: chiudi }),
        el("span", { class: "titolo-finestra", text: sv ? "Modifica sveglia" : "Aggiungi sveglia" }),
        el("button", { class: "salva", text: "Salva", onclick: salva })
      ),
      el("div", { class: "scegli-ora" }, inputOra),
      el(
        "div",
        { class: "gruppo" },
        el("div", { class: "voce" }, el("span", { text: "Ripeti" }), ripeti),
        el("div", { class: "giorni" }, ...cerchi)
      ),
      el(
        "div",
        { class: "gruppo" },
        el("label", { class: "voce" }, el("span", { text: "Nome" }), inputNome),
        el("label", { class: "voce" }, el("span", { text: "Suona su" }), sceltaDisp),
        el("div", { class: "voce" }, el("span", { text: "Volume graduale" }),
          interruttore(stato.progressiva, (v) => (stato.progressiva = v), "Volume graduale")),
        el("div", { class: "voce" }, el("span", { text: "Salta i festivi" }), festivi),
        el("label", { class: "voce" }, el("span", { text: "Suona per" }), sceltaDurata)
      ),
      el("div", { class: "nota", text: "Si ferma con “Alexa, stop” o da sola dopo la durata scelta." }),
      errore,
      sv
        ? el("button", {
            class: "elimina",
            text: "Elimina sveglia",
            onclick: async () => {
              try {
                await this._comando({ type: "sveglie/elimina", sveglia: sv.id });
                chiudi();
              } catch (e) {
                errore.textContent = this._errore;
              }
            },
          })
        : null
    );
    const velo = el("div", { class: "velo", onclick: chiudi }, finestra);
    velo.addEventListener("keydown", (ev) => ev.key === "Escape" && chiudi());
    this._finestra = { nodo: velo };
    this._disegna();
  }
}

if (!customElements.get("sveglie-card")) {
  customElements.define("sveglie-card", SveglieCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "sveglie-card",
    name: "Sveglie",
    description: "Le sveglie di casa: elenco, aggiungi, modifica e salta la prossima.",
    preview: true,
  });
}
