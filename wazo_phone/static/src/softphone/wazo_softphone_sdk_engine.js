/**
 * Moteur SIP adossé au **SDK officiel Wazo** (P3.3f).
 *
 * P3.3f compare deux moteurs possibles pour la signalisation + les médias :
 *
 * 1. **SIP.js brut** (notre code P3.3a/b) — nous écrivons nous-mêmes le
 *    cycle de vie, et tout ce qui n'est pas écrit manque. Relevé pendant
 *    cette phase : le chemin SIP.js brut ne câblait **aucun élément audio
 *    distant** — il se connectait, mais restait muet.
 * 2. **`WebRTCClient` du SDK** (ce module) — le SDK fournit l'attachement du
 *    média distant (`ON_TRACK` / `createAudioElementFor`), la détection
 *    d'IP privée pour l'ICE, le heartbeat de transport, la reconnexion ICE,
 *    les statistiques réseau, et gère conference/vidéo dans hold/transfert.
 *
 * Faits qui ont tranché (relevés sur l'artefact `@wazo/sdk` 0.49.5) :
 *
 * * le SDK **dépend de `sip.js@^0.21.2`** — la version exacte que nous
 *   vendorisons : ce n'est pas un fork, la pile SIP ne change pas ;
 * * il publie un bundle **UMD** `dist/wazo-sdk.js` avec toutes ses
 *   dépendances inlinées → vendorisable sans étape de build ;
 * * il **construit lui-même** l'URL WebSocket :
 *   ``wss://<hôte>:<port>/api/asterisk/ws``. Il faut donc lui passer un
 *   **hôte** et un **port** : lui donner une URL complète le fait dériver
 *   (il découpe ``websocketSip`` sur ``:`` et prendrait ``wss`` pour l'hôte) ;
 * * il construit l'URI/From depuis ``authorizationUser``
 *   (``sip:<authorizationUser>@<hôte>``) → cette option doit porter **l'AOR
 *   (nom d'endpoint)**, pas l'extension (piège P3.2) ;
 * * ``CONNECTED``/``DISCONNECTED`` sont des événements de **transport**,
 *   l'appel établi est signalé par ``ACCEPTED`` ;
 * * ``sendDTMF`` prend **une seule touche** par appel.
 *
 * Le SDK est **injecté** (``sdk``) et l'horloge de frappe DTMF est
 * paramétrable, ce qui rend ce module testable hors navigateur — voir
 * ``static/tests/wazo_softphone_sdk_engine.test.js``.
 */

/**
 * Événements du SDK et leurs valeurs de repli.
 *
 * Les constantes sont portées par l'instance (``client.INVITE``…) : on les
 * lit sur l'instance quand elles existent, sinon on retombe sur ces valeurs
 * (relevées sur la version 0.49.5).
 */
export const SDK_EVENTS = Object.freeze({
    REGISTERED: "registered",
    UNREGISTERED: "unregistered",
    REGISTRATION_FAILED: "registrationFailed",
    INVITE: "invite",
    ACCEPTED: "accepted",
    CONNECTED: "connected",
    DISCONNECTED: "disconnected",
    TRANSPORT_ERROR: "transportError",
    ON_TRACK: "onTrack",
    ON_ERROR: "onError",
});

/** Délai par défaut entre deux touches DTMF (ms) — comme une frappe réelle. */
export const DEFAULT_DTMF_DELAY_MS = 120;

/**
 * Extrait l'hôte et le port d'une URL WebSocket.
 *
 * Le SDK reconstruit l'URL complète (``/api/asterisk/ws``) à partir de
 * l'hôte et du port : c'est le seul découpage dont il a besoin.
 *
 * @param {string} url
 * @returns {?{host: string, port: number}}
 */
export function parseWssUrl(url) {
    if (!url || typeof url !== "string") {
        return null;
    }
    const match = url.match(/^(wss?|https?):\/\/([^/:?#]+)(?::(\d+))?/i);
    if (!match) {
        return null;
    }
    const scheme = match[1].toLowerCase();
    const secure = scheme === "wss" || scheme === "https";
    return {
        host: match[2],
        port: match[3] ? Number(match[3]) : secure ? 443 : 80,
    };
}

/**
 * Traduit la configuration softphone d'Odoo en configuration du SDK.
 *
 * @param {object} config configuration servie par Odoo
 * @returns {object} configuration ``WebRTCClient``
 */
export function sdkConfigFrom(config) {
    const cfg = config || {};
    const server = parseWssUrl(cfg.ws_url) || { host: cfg.domain, port: 443 };
    return {
        displayName: cfg.display_name || cfg.auth_user || "",
        host: server.host,
        port: server.port,
        media: { audio: true },
        // L'AOR (nom d'endpoint) : le SDK en dérive aussi l'URI/From.
        authorizationUser: cfg.aor || cfg.auth_user,
        password: cfg.auth_password || "",
        userAgentString: "Odoo Wazo SDK",
    };
}

export class WazoSdkEngine {
    /**
     * @param {object} options
     * @param {object} options.config configuration softphone d'Odoo
     * @param {object} options.sdk objet SDK (``window.WazoSDK``)
     * @param {function} [options.onEvent] récepteur d'événements normalisés
     * @param {number} [options.dtmfDelayMs] délai entre deux touches DTMF
     */
    constructor({ config, sdk, onEvent, dtmfDelayMs = DEFAULT_DTMF_DELAY_MS } = {}) {
        this.config = config;
        this.sdk = sdk;
        this.onEvent = onEvent || (() => {});
        this.dtmfDelayMs = dtmfDelayMs;
        /** @type {?object} */
        this.client = null;
        /** @type {?object} */
        this.session = null;
        this.sessionId = null;
        this._watched = false;
    }

    /** Une session est-elle en cours ? */
    get hasSession() {
        return Boolean(this.session);
    }

    /**
     * Construit le client WebRTC et attend l'enregistrement.
     *
     * @returns {Promise<boolean>} ``true`` si l'enregistrement a abouti.
     */
    async start() {
        const Client = this.sdk?.WebRTCClient;
        if (typeof Client !== "function") {
            this._emit("error", { message: "SDK Wazo indisponible." });
            return false;
        }
        let client;
        try {
            client = new Client(sdkConfigFrom(this.config));
        } catch (error) {
            this._emit("error", { message: error?.message || String(error) });
            return false;
        }
        this.client = client;
        this._bind(client);
        try {
            await client.waitForRegister();
        } catch (error) {
            this._emit("error", { message: error?.message || String(error) });
            return false;
        }
        return true;
    }

    /** Ferme le client (et donc le transport). */
    async stop() {
        const client = this.client;
        this._clearSession();
        this.client = null;
        if (client && typeof client.close === "function") {
            try {
                await client.close(true);
            } catch (error) {
                // La fermeture ne doit jamais faire échouer l'arrêt.
            }
        }
    }

    /**
     * @param {string} target extension à appeler
     * @returns {Promise<boolean>}
     */
    async call(target) {
        if (!this.client || !target) {
            return false;
        }
        // ``call(number, enableVideo, audioOnly, conference, options)`` :
        // le softphone est audio-only.
        const session = this.client.call(String(target), false, true, false, {});
        if (!session) {
            this._emit("error", { message: "Appel refusé par le SDK." });
            return false;
        }
        this._adoptSession(session);
        return true;
    }

    /** Répond à l'appel entrant. */
    async answer() {
        if (!this.client || !this.session) {
            return false;
        }
        try {
            await this.client.answer(this.session);
        } catch (error) {
            this._emit("error", { message: error?.message || String(error) });
            return false;
        }
        return true;
    }

    /** Raccroche. */
    async hangup() {
        const client = this.client;
        const session = this.session;
        if (!client || !session) {
            return false;
        }
        try {
            await client.hangup(session);
        } catch (error) {
            this._emit("error", { message: error?.message || String(error) });
        }
        this._clearSession();
        if (!this._watched) {
            // Sans observateur de session (SDK d'une autre version), c'est
            // nous qui signalons la fin d'appel.
            this._emit("ended");
        }
        return true;
    }

    /** Met l'appel en attente. */
    async hold() {
        return this._sessionCommand("hold");
    }

    /** Reprend l'appel. */
    async unhold() {
        return this._sessionCommand("unhold");
    }

    /**
     * Émet une séquence DTMF.
     *
     * ``WebRTCClient.sendDTMF`` ne prend **qu'une touche** : on boucle, avec
     * un délai entre les touches pour rester proche d'une frappe réelle.
     *
     * @param {string} tones séquence (ex. « 1234* »)
     * @returns {Promise<boolean>}
     */
    async sendDtmf(tones) {
        if (!this.client || !this.session || !tones) {
            return false;
        }
        const sequence = String(tones);
        for (let index = 0; index < sequence.length; index++) {
            if (index > 0 && this.dtmfDelayMs > 0) {
                await new Promise((resolve) => setTimeout(resolve, this.dtmfDelayMs));
            }
            this.client.sendDTMF(this.session, sequence[index]);
        }
        return true;
    }

    /**
     * Transfert (REFER) vers ``target``.
     *
     * @param {string} target
     * @returns {Promise<boolean>}
     */
    async transfer(target) {
        if (!this.client || !this.session || !target) {
            return false;
        }
        try {
            this.client.transfer(this.session, String(target));
        } catch (error) {
            this._emit("error", { message: error?.message || String(error) });
            return false;
        }
        return true;
    }

    // ─── Internes ────────────────────────────────────────────────────────────

    async _sessionCommand(name) {
        if (!this.client || !this.session) {
            return false;
        }
        const method = this.client[name];
        if (typeof method !== "function") {
            return false;
        }
        try {
            await method.call(this.client, this.session);
        } catch (error) {
            this._emit("error", { message: error?.message || String(error) });
            return false;
        }
        return true;
    }

    _adoptSession(session) {
        this.session = session;
        this.sessionId = session?.id ?? null;
        this._watchSession(session);
    }

    _clearSession() {
        this.session = null;
        this.sessionId = null;
        this._watched = false;
    }

    /**
     * Observe la session pour signaler une fin d'appel distante.
     *
     * @param {?object} session
     */
    _watchSession(session) {
        if (!session || !session.stateChange || typeof session.stateChange.addListener !== "function") {
            this._watched = false;
            return;
        }
        this._watched = true;
        session.stateChange.addListener((event) => {
            const state = event?.newState ?? event;
            if (state === "Terminated") {
                this._clearSession();
                this._emit("ended");
            }
        });
    }

    /**
     * Valeur d'une constante d'événement : l'instance fait foi, sinon repli.
     *
     * @param {string} name
     * @returns {string}
     */
    _event(name) {
        const fromInstance = this.client ? this.client[name] : undefined;
        return typeof fromInstance === "string" ? fromInstance : SDK_EVENTS[name];
    }

    _bind(client) {
        const on = (name, handler) => {
            const event = this._event(name);
            if (event && typeof client.on === "function") {
                client.on(event, handler);
            }
        };
        on("REGISTERED", () => this._emit("registered"));
        on("UNREGISTERED", () => this._emit("unregistered"));
        on("REGISTRATION_FAILED", (error) =>
            this._emit("registration_failed", { error })
        );
        on("INVITE", (session) => {
            this._adoptSession(session);
            this._emit("incoming", this._callerInfo(session));
        });
        // ``ACCEPTED`` = appel établi. ``CONNECTED``/``DISCONNECTED`` sont
        // des événements de TRANSPORT, pas d'appel.
        on("ACCEPTED", (session) => {
            if (!this.session && session) {
                this._adoptSession(session);
            }
            this._emit("in_call");
        });
        on("ON_TRACK", () => this._emit("track"));
        on("TRANSPORT_ERROR", (error) => this._emit("transport_lost", { error }));
        on("DISCONNECTED", (error) => this._emit("transport_lost", { error }));
        on("ON_ERROR", (error) => this._emit("error", { error }));
    }

    /**
     * Identité de l'appelant (le SDK sait lire le numéro d'une invitation).
     *
     * @param {?object} session
     * @returns {object}
     */
    _callerInfo(session) {
        let from = "";
        try {
            from = this.client?.getNumber?.(session) || "";
        } catch (error) {
            from = "";
        }
        return { from, name: "" };
    }

    _emit(type, payload) {
        this.onEvent(type, payload);
    }
}
