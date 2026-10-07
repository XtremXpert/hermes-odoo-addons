/**
 * Moteur SIP « SIP.js écrit à la main » (P3.3a/b), derrière l'interface
 * commune des moteurs (voir ``wazo_softphone_engine.js``).
 *
 * Ce code vivait dans le service ; il est sorti ici pour que le service
 * puisse **choisir son moteur** (P3.3f) sans que la machine d'état, la
 * réactivité d'UI et l'arbitrage multi-onglets en dépendent.
 *
 * **Réserve connue, assumée et documentée** : ce moteur n'attache **aucun
 * élément audio distant**. Un appel s'établit, mais on n'entend rien. C'est
 * précisément ce qui a fait retenir le moteur du SDK officiel
 * (``wazo_softphone_sdk_engine.js``) ; celui-ci n'est conservé que comme
 * repli de comparaison. Ne pas le déployer en croyant qu'il « marche parce
 * que l'appel est établi ».
 *
 * Le global ``SIP`` est **injecté** : ce module est testable hors navigateur
 * (voir ``static/tests/wazo_softphone_sipjs_engine.test.js``).
 */
export class SipJsEngine {
    /**
     * @param {Object} options
     * @param {Object} options.config configuration softphone d'Odoo
     * @param {Object} options.sip global ``SIP`` du bundle vendorisé
     * @param {function} [options.onEvent] récepteur d'événements normalisés
     * @param {Number} [options.reconnectDelayMs] délai avant reconnexion
     *   après une perte de transport (``0`` = pas de reconnexion).
     */
    constructor({config, sip, onEvent, reconnectDelayMs = 2000} = {}) {
        this.config = config;
        this.sip = sip;
        this.onEvent =
            onEvent ||
            (() => {
                // Aucun récepteur : les événements sont ignorés.
            });
        this.reconnectDelayMs = reconnectDelayMs;
        this.userAgent = null;
        this.registerer = null;
        this.session = null;
        this._watched = false;
        this._stopped = false;
    }

    /** Une session est-elle en cours ? */
    get hasSession() {
        return Boolean(this.session);
    }

    /**
     * Démarre le transport puis enregistre le compte.
     *
     * @returns {Promise<boolean>}
     */
    async start() {
        const SIP = this.sip;
        if (!SIP || typeof SIP.UserAgent !== "function") {
            this._emit("error", {message: "Client SIP.js indisponible."});
            return false;
        }
        this._stopped = false;
        try {
            this.userAgent = this._createUserAgent(SIP);
            await this.userAgent.start();
        } catch (error) {
            this.userAgent = null;
            this._emit("error", {message: error?.message || String(error)});
            return false;
        }
        this.registerer = this._createRegisterer(SIP);
        try {
            await this.registerer.register();
        } catch (response) {
            // 401 = identifiants refusés ; le reste = échec d'enregistrement.
            this._emit("registration_failed", {
                statusCode: response?.message?.statusCode,
            });
            return false;
        }
        // Pas d'émission ici : le changement d'état du Registerer est la
        // source unique (sinon l'enregistrement serait signalé deux fois —
        // une fois par la promesse, une fois par « Registered »).
        return true;
    }

    /** Désenregistre et arrête le transport. */
    async stop() {
        this._stopped = true;
        this._clearSession();
        if (this.registerer) {
            try {
                await this.registerer.unregister();
            } catch {
                // Ignoré
            }
            this.registerer = null;
        }
        if (this.userAgent) {
            try {
                this.userAgent.stop();
            } catch {
                // Ignoré
            }
            this.userAgent = null;
        }
    }

    /**
     * @param {String} target extension à appeler
     * @returns {Promise<boolean>}
     */
    async call(target) {
        const SIP = this.sip;
        if (!SIP || !this.userAgent || !target) {
            return false;
        }
        const targetUri = SIP.UserAgent.makeURI(`sip:${target}@${this.config.domain}`);
        let session = null;
        try {
            session = new SIP.Inviter(this.userAgent, targetUri, {});
        } catch (error) {
            this._emit("error", {message: error?.message || String(error)});
            return false;
        }
        this._adoptSession(session);
        try {
            await session.invite();
        } catch (error) {
            this._emit("error", {message: error?.message || String(error)});
            return false;
        }
        return true;
    }

    /** Répond à l'appel entrant. */
    async answer() {
        if (!this.session || typeof this.session.accept !== "function") {
            return false;
        }
        try {
            await this.session.accept();
        } catch (error) {
            this._emit("error", {message: error?.message || String(error)});
            return false;
        }
        this._emit("in_call");
        return true;
    }

    /** Raccroche. */
    async hangup() {
        const session = this.session;
        if (!session || typeof session.bye !== "function") {
            return false;
        }
        try {
            await session.bye();
        } catch (error) {
            this._emit("error", {message: error?.message || String(error)});
        }
        this._clearSession();
        if (!this._watched) {
            this._emit("ended");
        }
        return true;
    }

    /** Met l'appel en attente (re-INVITE SDP, RFC 6337). */
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
     * Contrairement au SDK (une touche par appel), ``Session.sendDtmf`` de
     * SIP.js accepte la séquence complète.
     *
     * @param {String} tones
     * @returns {Promise<boolean>}
     */
    async sendDtmf(tones) {
        if (!this.session || !tones || typeof this.session.sendDtmf !== "function") {
            return false;
        }
        try {
            await this.session.sendDtmf(String(tones));
        } catch (error) {
            this._emit("error", {message: error?.message || String(error)});
            return false;
        }
        return true;
    }

    /**
     * Transfert (REFER, RFC 3515).
     *
     * @param {String} target
     * @returns {Promise<boolean>}
     */
    async transfer(target) {
        const SIP = this.sip;
        const session = this.session;
        if (!SIP || !session || !target || typeof session.refer !== "function") {
            return false;
        }
        try {
            const targetUri = SIP.UserAgent.makeURI(
                `sip:${target}@${this.config.domain}`
            );
            await session.refer(targetUri);
        } catch (error) {
            this._emit("error", {message: error?.message || String(error)});
            return false;
        }
        return true;
    }

    // ─── Internes ────────────────────────────────────────────────────────────

    async _sessionCommand(name) {
        const session = this.session;
        if (!session || typeof session[name] !== "function") {
            return false;
        }
        try {
            await session[name]();
        } catch (error) {
            this._emit("error", {message: error?.message || String(error)});
            return false;
        }
        return true;
    }

    _createUserAgent(SIP) {
        const cfg = this.config;
        // Découverte P3.2 : le From/AOR est le nom de l'endpoint généré
        // (``cfg.aor``), distinct de l'username d'authentification.
        const uri = SIP.UserAgent.makeURI(`sip:${cfg.aor}@${cfg.domain}`);
        return new SIP.UserAgent({
            authorizationPassword: cfg.auth_password,
            authorizationUsername: cfg.auth_user,
            delegate: {
                onInvite: (session) => this._onInvite(session),
                onDisconnect: (error) => this._onTransportLost(error),
            },
            transportOptions: {
                keepAliveInterval: 20,
                server: cfg.ws_url,
            },
            uri,
            userAgentString: `Odoo Wazo SIP.js/${SIP.version}`,
        });
    }

    _createRegisterer(SIP) {
        const registerer = new SIP.Registerer(this.userAgent, {expires: 600});
        registerer.stateChange.addListener((event) =>
            this._onRegistererState(event.newState)
        );
        return registerer;
    }

    _onRegistererState(newState) {
        const SIP = this.sip;
        if (newState === SIP.RegistererState.Registered) {
            this._emit("registered");
        } else if (newState === SIP.RegistererState.Unregistered) {
            this._emit("unregistered");
        }
    }

    _onInvite(session) {
        this._adoptSession(session);
        this._emit("incoming", this._callerInfo(session));
    }

    /**
     * Identité de l'appelant (en-tête ``From`` décodé par SIP.js).
     *
     * @param {?object} session
     * @returns {Object}
     */
    _callerInfo(session) {
        const identity = session?.remoteIdentity;
        return {
            from: identity?.uri?.user || "",
            name: identity?.displayName || "",
        };
    }

    _adoptSession(session) {
        this.session = session;
        this._watchSession(session);
    }

    _clearSession() {
        this.session = null;
        this._watched = false;
    }

    /**
     * Observe la session (établie / terminée).
     *
     * @param {?object} session
     */
    _watchSession(session) {
        const SIP = this.sip;
        if (
            !session ||
            !session.stateChange ||
            typeof session.stateChange.addListener !== "function"
        ) {
            this._watched = false;
            return;
        }
        this._watched = true;
        session.stateChange.addListener((event) => {
            if (event.newState === SIP.SessionState.Established) {
                this._emit("in_call");
            } else if (event.newState === SIP.SessionState.Terminated) {
                this._clearSession();
                this._emit("ended");
            }
        });
    }

    _onTransportLost(error) {
        if (this._stopped) {
            return;
        }
        this._emit("transport_lost", {error});
        if (this.reconnectDelayMs > 0) {
            setTimeout(() => this.userAgent?.reconnect?.(), this.reconnectDelayMs);
        }
    }

    _emit(type, payload) {
        this.onEvent(type, payload);
    }
}
