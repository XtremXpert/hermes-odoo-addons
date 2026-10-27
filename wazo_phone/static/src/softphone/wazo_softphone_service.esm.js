/**
 * Service softphone Wazo (P3.3).
 *
 * Cerveau du softphone : lit la configuration du navigateur (via le RPC
 * ``res.users.get_wazo_softphone_config``), pilote un **moteur SIP**
 * interchangeable (voir plus bas), expose les méthodes d'appel, la réactivité
 * d'UI (affichage/overlay) et émet les événements d'état (via ``bus``).
 *
 * **Arbitrage multi-onglets (P3.3e).** Le navigateur ouvre volontiers
 * plusieurs onglets Odoo : sans arbitrage, chacun s'enregistrerait et
 * sonnerait. Le service délègue donc la propriété de la couche SIP à
 * ``SoftphoneArbiter`` : **un seul onglet** enregistre, les autres sont des
 * télécommandes du même appel (leurs commandes remontent au propriétaire).
 * Voir ``wazo_softphone_arbiter.js``.
 *
 * **Connexion directe à Wazo.** Le navigateur parle à l'endpoint WebRTC de
 * Wazo (``wss://<hôte>/api/asterisk/ws``) ; il n'y a **aucun relay** dans
 * le chemin (spec P3 v3, section NORMATIF).
 *
 * **Moteur interchangeable (P3.3f).** Le service ne parle pas directement à
 * SIP.js : il reçoit un **moteur** (``wazo_softphone_engine.js``) et lui
 * délègue tout ce qui touche à la signalisation et aux médias. Deux moteurs
 * existent — le SDK officiel Wazo (retenu) et la couche SIP.js écrite à la
 * main (repli) — et le choix vient du paramètre ``wazo.softphone_engine``,
 * porté par la configuration servie par le backend : changer de moteur ne
 * demande donc pas de redéployer du code.
 *
 * Le client SIP.js (exposé comme global ``SIP``) est fourni par le bundle
 * ``wazo_phone.assets_sip``. Le service se dégrade proprement si ce bundle
 * n'est pas chargé (``SIP`` absent) : l'UI reste utilisable, seule la couche
 * SIP est désactivée.
 */
import {EventBus, proxy} from "@odoo/owl";
import {loadBundle} from "@web/core/assets";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";

import {SoftphoneArbiter} from "./wazo_softphone_arbiter.esm.js";
import {
    buildCallInfo,
    finalizePayload,
    isDuplicateIncoming,
    isEmptyMissedNotice,
} from "./wazo_call_flow.esm.js";
import {
    createEngine,
    engineBundleName,
    isEngineLoaded,
} from "./wazo_softphone_engine.esm.js";

const STATES = Object.freeze({
    IDLE: "idle",
    CONNECTING: "connecting",
    REGISTERING: "registering",
    REGISTERED: "registered",
    UNREGISTERED: "unregistered",
    ERROR: "error",
    OUTBOUND: "outbound",
    RINGING: "ringing",
    IN_CALL: "in_call",
    ENDED: "ended",
});

/**
 * @typedef {Object} SoftphoneConfig
 * @property {String} ws_url
 * @property {String} aor
 * @property {String} auth_user
 * @property {String} auth_password
 * @property {String} domain
 * @property {String} display_name
 * @property {number|string} extension
 * @property {Boolean} enabled
 */

export class WazoSoftphoneService {
    /** @type {import("@odoo/owl").Env} */
    env;
    /** @type {import("@odoo/owl").EventBus} */
    bus = new EventBus();
    /** @type {Boolean} */
    isUnloading = false;
    /** @type {?SoftphoneConfig} */
    config = null;

    /**
     * État réactif du service (consommé par l'UI via ``proxy(this)``).
     * @type {import("@odoo/owl").Reactive}
     */
    status;

    /**
     * @type {import("@odoo/owl").Reactive}
     */
    ui;

    /** @type {?object} moteur SIP courant (voir ``wazo_softphone_engine.js``) */
    engine = null;
    /** @type {Boolean} démarrage du moteur en cours (anti-double) */
    startingSip = false;

    /**
     * @param {import("@odoo/owl").Env} env
     * @param {Object} services
     */
    constructor(env, services) {
        this.env = env;
        this.orm = services.orm;
        this.notification = services.notification;
        this.busService = services.bus_service;
        this.status = proxy({
            state: STATES.IDLE,
            message: "",
            currentCall: null,
            held: false,
        });
        // Journal d'appels (CDR) de l'utilisateur, le plus récent d'abord.
        this.callLog = proxy([]);
        this.ui = proxy({
            isDisplayed: false,
            shouldBeOnTop: false,
        });
        // ── Arbitrage multi-onglets (P3.3e) ──────────────────────────────
        // Le verrou Web Locks (et le canal de diffusion) sont natifs au
        // navigateur ; on les passe en adaptateurs pour que la logique soit
        // testable hors navigateur (voir static/tests/).
        this.arbiter = new SoftphoneArbiter({
            tabId: `tab-${Date.now().toString(36)}-${Math.random()
                .toString(36)
                .slice(2, 8)}`,
            locks: typeof navigator !== "undefined" ? navigator.locks : null,
            createChannel:
                typeof BroadcastChannel !== "undefined"
                    ? (name) => new BroadcastChannel(name)
                    : null,
        });
        // Propriétaire désigné (ou reprise après fermeture de l'onglet qui
        // détenait la couche SIP) → c'est lui qui démarre/arrête SIP.
        this.arbiter.onLeadership = (isLeader) => {
            if (isLeader) {
                this._startSip();
            } else {
                this._disposeSip();
            }
        };
        // Appel entrant relayé par le propriétaire : l'onglet sonne.
        this.arbiter.onIncoming = (info) => this._onRemoteIncoming(info);
        // Télécommande → propriétaire : c'est lui qui touche la session.
        this.arbiter.onCommand = (name, payload) =>
            this._runRemoteCommand(name, payload);
        // Télécommande ← propriétaire : refléter l'état de l'appel.
        this.arbiter.onState = (state) => this._applyRemoteState(state);
        // ── Notifications bus Odoo (P3.3g) ───────────────────────────────
        // Chaque session de l'utilisateur est déjà abonnée à son canal
        // ``res.users`` : l'onglet qui détient le SIP y relaie l'appel
        // entrant, et ``finalize_wazo_call`` y signale les appels manqués.
        // Utile aux appareils sans endpoint enregistré — le BroadcastChannel
        // ne couvre que les onglets du même navigateur.
        if (this.busService) {
            this.busService.subscribe("wazo_phone.incoming_call", (payload) =>
                this._onBusIncomingCall(payload)
            );
            this.busService.subscribe("wazo_phone.missed_call", (payload) =>
                this._onBusMissedCall(payload)
            );
        }
        window.addEventListener("beforeunload", () => {
            this.isUnloading = true;
            this._disposeSip();
        });
        return proxy(this);
    }

    // ─── État d'UI (consommé par l'app / le systray) ─────────────────────────

    /** @returns {Boolean} */
    get isDisplayed() {
        return this.ui.isDisplayed;
    }

    /** @returns {Boolean} */
    get shouldBeOnTop() {
        // Un appel entrant passe au-dessus des dialogs ouverts.
        return this.state === STATES.RINGING;
    }

    /**
     * Cet onglet détient-il la couche SIP ?
     *
     * @returns {Boolean} ``false`` = un autre onglet gère le téléphone.
     */
    get isPhoneOwner() {
        return this.arbiter.isLeader;
    }

    /** Cet onglet doit-il relayer ses commandes au propriétaire ? */
    get isRemoteControl() {
        return this.arbiter.shouldForward;
    }

    showSoftphone() {
        this.ui.isDisplayed = true;
        this.ui.shouldBeOnTop = this.state === STATES.RINGING;
        this.bus.trigger("display_changed");
    }

    hideSoftphone() {
        this.ui.isDisplayed = false;
        this.bus.trigger("display_changed");
    }

    toggleSoftphone() {
        if (this.isDisplayed) {
            this.hideSoftphone();
        } else {
            this.showSoftphone();
        }
    }

    // ─── Capacités / config ───────────────────────────────────────────────────

    /**
     * Vérifie le support WebRTC du navigateur.
     *
     * @returns {Boolean}
     */
    get hasRtcSupport() {
        return Boolean(
            window.RTCPeerConnection && window.MediaStream && navigator.mediaDevices
        );
    }

    /**
     * Vérifie si la configuration est chargée et utilisable.
     *
     * @returns {Boolean}
     */
    get isConfigured() {
        return Boolean(
            this.config && this.config.enabled && this.config.ws_url && this.config.aor
        );
    }

    /**
     * Le global du moteur configuré est-il chargé sur la page ?
     *
     * @returns {Boolean}
     */
    get engineAvailable() {
        return isEngineLoaded(this.config?.engine, this._scope());
    }

    /**
     * Nom du bundle d'assets du moteur configuré (chargé à la demande).
     *
     * @returns {String}
     */
    get engineBundle() {
        return engineBundleName(this.config?.engine);
    }

    /**
     * Une session d'appel est-elle en cours (portée par le moteur) ?
     *
     * @returns {Boolean}
     */
    get hasSession() {
        return Boolean(this.engine && this.engine.hasSession);
    }

    /**
     * Portée des globaux (``window`` en navigateur).
     *
     * @returns {Object}
     */
    _scope() {
        return typeof window !== "undefined" ? window : globalThis;
    }

    /**
     * État courant (réactif).
     *
     * @returns {String}
     */
    get state() {
        return this.status.state;
    }

    /**
     * Charge la configuration softphone depuis le backend (RPC).
     *
     * @returns {Promise<?SoftphoneConfig>}
     */
    async loadConfig() {
        try {
            const config = await this.orm.call(
                "res.users",
                "get_wazo_softphone_config",
                [[]]
            );
            this.config = config || null;
            return this.config;
        } catch (error) {
            this.config = null;
            this._setState(
                STATES.ERROR,
                error.message || "Configuration non disponible"
            );
            return null;
        }
    }

    // ─── Cycle de vie SIP ─────────────────────────────────────────────────────

    /**
     * Démarre le softphone.
     *
     * L'arbitrage désigne l'onglet propriétaire de la couche SIP ; le
     * démarrage effectif est déclenché par ``onLeadership`` (un seul
     * REGISTER pour N onglets ouverts). Un onglet non propriétaire reste
     * utilisable en télécommande du même appel.
     *
     * @returns {Promise<void>}
     */
    async connect() {
        // Volontairement NON attendu : la promesse de verrou ne se résout
        // qu'à sa libération (fermeture de l'onglet, ou reprise du rôle).
        // L'attendre bloquerait un onglet télécommande indéfiniment.
        this.arbiter.start();
        // Unlock the audio context on the first user gesture: browsers refuse
        // autoplay sound until the user has interacted with the page once.
        document.addEventListener("click", () => {
            try {
                const AC = window.AudioContext || window.webkitAudioContext;
                if (!AC) {
                    return;
                }
                if (!this._audioCtx) {
                    this._audioCtx = new AC();
                }
                this._audioCtx.resume().catch(() => {});
            } catch (e) {
                // Audio unavailable (headless, blocked) — ringtone is optional.
            }
        }, {once: true});
        // La désignation est asynchrone côté navigateur (l'octroi du verrou
        // est remis à une tâche). Si, une boucle d'événements plus tard, on
        // n'est toujours pas propriétaire, c'est qu'un autre onglet l'est :
        // on se présente comme télécommande — l'appel reste pilotable d'ici.
        setTimeout(() => {
            if (!this.arbiter.isLeader) {
                this._setState(
                    STATES.IDLE,
                    _t("Téléphone géré par un autre onglet de ce navigateur.")
                );
            }
        }, 0);
    }

    /**
     * Arrête le softphone (déconnecte le transport, désenregistre).
     */
    disconnect() {
        this._disposeSip();
        this.arbiter.stop();
        this._setState(STATES.IDLE, "");
    }

    /**
     * Construit et démarre la couche SIP (propriétaire uniquement).
     *
     * @returns {Promise<void>}
     */
    async _startSip() {
        if (this.engine || this.startingSip) {
            return;
        }
        this.startingSip = true;
        try {
            if (!this.config) {
                await this.loadConfig();
            }
            if (!this.isConfigured) {
                this._setState(
                    STATES.ERROR,
                    _t("Softphone non configuré pour cet utilisateur.")
                );
                return;
            }
            if (!this.engineAvailable && !(await this._loadEngineBundle())) {
                return;
            }
            this._setState(STATES.CONNECTING, _t("Connexion…"));
            this.engine = this._createEngine();
            await this.engine.start();
        } finally {
            this.startingSip = false;
        }
    }

    /**
     * Construit le moteur décrit par la configuration.
     *
     * @returns {Object} moteur (voir ``wazo_softphone_engine.js``)
     */
    _createEngine() {
        return createEngine({
            name: this.config.engine,
            config: this.config,
            onEvent: (type, payload) => this._onEngineEvent(type, payload),
            scope: this._scope(),
        });
    }

    // ─── Appels ───────────────────────────────────────────────────────────────

    /**
     * Passe un appel sortant vers ``target`` (extension).
     *
     * @param {String} target
     * @returns {Promise<void>}
     */
    async callOut(target) {
        if (this.arbiter.shouldForward) {
            this.arbiter.forwardCommand("call", {target});
            return;
        }
        await this._ensureEngine();
        if (!this.engine) {
            return;
        }
        // Suivi de l'appel pour le bouclage (note sur le contact à la fin).
        this.postCall = null;
        this.status.currentCall = buildCallInfo({direction: "outbound", num: target});
        this._setState(STATES.OUTBOUND, _t("Appel en cours vers %(target)s", {target}));
        await this.engine.call(target);
    }

    /**
     * Répond à un appel entrant.
     *
     * Décrocher **revendique** l'appel : le premier onglet qui répond
     * l'emporte, les autres passent en télécommande (sinon l'appel serait
     * répondu deux fois).
     *
     * @returns {Promise<void>}
     */
    async answer() {
        if (!this.arbiter.claim()) {
            return;
        }
        if (this.arbiter.shouldForward) {
            this.arbiter.forwardCommand("answer");
            return;
        }
        await this.engine?.answer();
    }

    /**
     * Raccroche (termine la session courante).
     *
     * @returns {Promise<void>}
     */
    async hangup() {
        if (this.arbiter.shouldForward) {
            this.arbiter.forwardCommand("hangup");
            return;
        }
        await this.engine?.hangup();
    }

    // ─── Cœur d'appel : hold / transfer / DTMF (P3.3b) ──────────────────────

    /**
     * Met la session en hold (re-INVITE SDP, RFC 6337) : le correspondant
     * n'entend plus le locuteur local.
     *
     * @returns {Promise<void>}
     */
    async hold() {
        if (this.arbiter.shouldForward) {
            this.arbiter.forwardCommand("hold");
            return;
        }
        if (await this.engine?.hold()) {
            this.status.held = true;
        }
    }

    /**
     * Reprend la session (annule le hold).
     *
     * @returns {Promise<void>}
     */
    async unhold() {
        if (this.arbiter.shouldForward) {
            this.arbiter.forwardCommand("unhold");
            return;
        }
        if (await this.engine?.unhold()) {
            this.status.held = false;
        }
    }

    /**
     * Émet une séquence DTMF (touches 0-9, *, #) sur la session établie.
     *
     * @param {String} tones séquence DTMF (ex. "1234*")
     * @returns {Promise<void>}
     */
    async sendDtmf(tones) {
        if (this.arbiter.shouldForward) {
            this.arbiter.forwardCommand("dtmf", {tones});
            return;
        }
        await this.engine?.sendDtmf(tones);
    }

    /**
     * Transfert en bande latérale (REFER, RFC 3515) : demande à la session
     * courante d'être connectée à ``target``.
     *
     * @param {String} target extension de transfert
     * @returns {Promise<void>}
     */
    async transfer(target) {
        if (this.arbiter.shouldForward) {
            this.arbiter.forwardCommand("transfer", {target});
            return;
        }
        await this.engine?.transfer(target);
    }

    // ─── Journal d'appels (P3.3b) ────────────────────────────────────────────

    /**
     * Charge le journal d'appels (CDR) de l'utilisateur depuis le backend.
     *
     * @param {Number} [limit=50]
     * @returns {Promise<number>} nombre d'entrées chargées
     */
    async loadCallLog(limit = 50) {
        try {
            const entries = await this.orm.call("res.users", "get_wazo_call_log", [
                [],
                limit,
            ]);
            this.callLog = proxy(entries || []);
            return (entries || []).length;
        } catch {
            this.callLog = proxy([]);
            return 0;
        }
    }

    // ─── Moteur : démarrage à la demande et événements ──────────────────────

    /**
     * S'assure qu'un moteur est démarré avant une commande d'appel.
     *
     * @returns {Promise<void>}
     */
    async _ensureEngine() {
        if (!this.engine) {
            await this._startSip();
        }
    }

    /**
     * Applique un événement du moteur au cycle de vie du softphone.
     *
     * Le moteur est la seule source de vérité sur la signalisation ; le
     * service en déduit son état (et le diffuse aux autres onglets).
     *
     * @param {String} type
     * @param {Object} [payload]
     */
    _onEngineEvent(type, payload) {
        const info = payload || {};
        switch (type) {
            case "registered":
                this._setState(STATES.REGISTERED, _t("Prêt"));
                break;
            case "unregistered":
                this._setState(STATES.UNREGISTERED, _t("Désenregistré"));
                break;
            case "registration_failed":
                this._setState(
                    STATES.ERROR,
                    info.statusCode === 401
                        ? _t("Authentification refusée. Vérifiez les identifiants.")
                        : _t("Échec de l'enregistrement.")
                );
                break;
            case "incoming":
                this.ui.shouldBeOnTop = true;
                this.status.currentCall = buildCallInfo({
                    direction: "inbound",
                    num: info.from,
                    name: info.name,
                });
                this._setState(
                    STATES.RINGING,
                    _t("Appel entrant de %(from)s", {
                        from: info.from || _t("inconnu"),
                    })
                );
                // Tous les onglets du navigateur doivent sonner : le
                // propriétaire diffuse l'appel, et le premier qui décroche
                // le revendique.
                this.arbiter.broadcastIncoming(info);
                // P3.3g : relais vers les AUTRES sessions de l'utilisateur
                // (autres navigateurs/appareils) via le bus Odoo. Le retour
                // de la notification sur nos propres onglets est ignoré —
                // ils sonnent déjà (déduplication côté réception).
                this._notifyIncomingToBackend(info);
                break;
            case "in_call":
                if (this.status.currentCall) {
                    this.status.currentCall.answered = true;
                }
                this._setState(STATES.IN_CALL, _t("En appel"));
                break;
            case "ended":
                this._onCallTerminated();
                break;
            case "transport_lost":
                if (!this.isUnloading) {
                    // La reconnexion est du ressort du moteur : il connaît
                    // son transport.
                    this._setState(STATES.ERROR, _t("Connexion perdue. Réessai…"));
                }
                break;
            case "track":
                // Le média distant est joué par le moteur (SDK) : rien à
                // faire côté service.
                break;
            case "error":
                this._setState(
                    STATES.ERROR,
                    info.message || _t("Erreur du moteur SIP.")
                );
                break;
            default:
                break;
        }
    }

    // ─── Télécommande (onglets non propriétaires) ───────────────────────────

    /**
     * Exécute une commande venue d'un onglet télécommande.
     *
     * @param {String} name
     * @param {Object} [payload]
     */
    async _runRemoteCommand(name, payload) {
        const args = payload || {};
        switch (name) {
            case "call":
                await this._ensureEngine();
                // Comme ``callOut`` : le suivi sert au bouclage (note sur
                // le contact) — un appel lancé en télécommande doit être
                // consigné comme les autres.
                this.status.currentCall = buildCallInfo({
                    direction: "outbound",
                    num: args.target,
                });
                return this.engine?.call(args.target);
            case "answer":
                return this.engine?.answer();
            case "hangup":
                return this.engine?.hangup();
            case "hold":
                return this.engine?.hold();
            case "unhold":
                return this.engine?.unhold();
            case "dtmf":
                return this.engine?.sendDtmf(args.tones);
            case "transfer":
                return this.engine?.transfer(args.target);
            default:
                return undefined;
        }
    }

    /**
     * Un autre onglet fait sonner un appel entrant.
     *
     * @param {?object} info
     */
    _onRemoteIncoming(info) {
        if (!info) {
            return;
        }
        this.ui.shouldBeOnTop = true;
        this._setState(
            STATES.RINGING,
            _t("Appel entrant de %(from)s", {from: info.from || _t("inconnu")})
        );
    }

    /**
     * Reflète l'état de session du propriétaire (sans le réémettre).
     *
     * @param {?object} state
     */
    _applyRemoteState(state) {
        if (!state || !state.state) {
            return;
        }
        // Keep the ringer in sync on remote tabs: ringing starts it, any
        // other state (in_call, ended, idle) stops it.
        if (state.state === STATES.RINGING) {
            this._startRingtone();
        } else {
            this._stopRingtone();
        }
        this.status.state = state.state;
        this.status.message = state.message || "";
        if (state.state === STATES.RINGING) {
            this.ui.shouldBeOnTop = true;
        }
        this.bus.trigger("state_changed", state);
    }

    // ─── Interne ───────────────────────────────────────────────────────────────

    /**
     * Charge le bundle d'assets du moteur configuré (lazy loading).
     *
     * Le bundle expose le global du moteur (``WazoSDK`` pour le SDK,
     * ``SIP`` pour SIP.js) après exécution. Sans lui, la couche d'appel est
     * indisponible et l'utilisateur est prévenu.
     *
     * @returns {Promise<boolean>} le global du moteur est-il disponible ?
     */
    async _loadEngineBundle() {
        const name = this.config?.engine;
        if (isEngineLoaded(name, this._scope())) {
            return true;
        }
        this._setState(STATES.CONNECTING, _t("Chargement du moteur SIP…"));
        try {
            await loadBundle(engineBundleName(name));
        } catch {
            this._setState(
                STATES.ERROR,
                _t("Échec du chargement du moteur SIP (bundle %(bundle)s).", {
                    bundle: engineBundleName(name),
                })
            );
            return false;
        }
        return isEngineLoaded(name, this._scope());
    }

    _onCallTerminated() {
        this.ui.shouldBeOnTop = false;
        this.status.held = false;
        this._setState(STATES.ENDED, _t("Appel terminé"));
        // Fin d'appel : on libère la revendication dans tous les onglets
        // (et on clôt l'appel entrant qu'ils affichaient).
        this.arbiter.release();
        // Bouclage : note sur le contact, appel manqué signalé (backend).
        this._finalizeCall();
        // Le CDR est écrit par Wazo après l'appel : on recharge le journal
        // pour qu'il apparaisse.
        this.loadCallLog();
        setTimeout(() => {
            if (this.state === STATES.ENDED) {
                this._setState(STATES.REGISTERED, _t("Prêt"));
            }
        }, 2000);
    }

    /**
     * Relaie l'appel entrant vers le canal bus de l'utilisateur (P3.3g).
     *
     * Volontairement sans attente ni remontée d'erreur : la sonnerie
     * locale ne dépend pas du backend, et une session injoignable ne doit
     * jamais empêcher de répondre.
     *
     * @param {Object} info charge utile de l'événement moteur « incoming »
     */
    _notifyIncomingToBackend(info) {
        this.orm
            .call("res.users", "notify_wazo_incoming_call", [
                [],
                {num: info.from, name: info.name || ""},
            ])
            .catch(() => {});
    }

    /**
     * Consigne la fin de l'appel courant auprès du backend.
     *
     * ``finalize_wazo_call`` identifie le contact, y dépose une note et, pour
     * un entrant manqué, crée l'activité « Appel » et diffuse la
     * notification « appel manqué » — qui revient ici par le bus et affiche
     * le toast. Le retour de la méthode sert à confirmer la note consignée.
     *
     * @returns {Promise<void>}
     */
    async _finalizeCall() {
        const payload = finalizePayload(this.status.currentCall);
        this.status.currentCall = null;
        if (!payload) {
            return;
        }
        try {
            const result = await this.orm.call("res.users", "finalize_wazo_call", [
                [],
                payload,
            ]);
            if (result && result.partner_name && !result.missed) {
                this.notification.add(
                    _t("Appel consigné sur la fiche de %(partner)s", {
                        partner: result.partner_name,
                    }),
                    {type: "info"}
                );
            }
            // Panneau post-appel : note, rappel, fiche contact.
            this.postCall = result && result.partner_id
                ? {
                      partnerId: result.partner_id,
                      partnerName: result.partner_name,
                      num: payload.num,
                      duration: payload.duration,
                  }
                : null;
        } catch {
            // Le bouclage est un confort : un échec ne doit jamais bloquer
            // la fin d'appel ni afficher d'erreur incompréhensible.
        }
    }

    /**
     * Notification bus « appel entrant » venue d'une autre session (P3.3g).
     *
     * @param {?Object} payload ``{num, name}``
     */
    async mute() {
        this.muted = await this._engineCmd("mute");
    }

    async unmute() {
        this.muted = !(await this._engineCmd("unmute"));
    }

    /** Parque l'appel dans le lot parking du tenant (transfert vers son exten). */
    async park() {
        const lots = await this.orm.searchRead(
            "wazo.parking", [], ["extension"], {limit: 1}
        );
        const target = lots.length && lots[0].extension ? lots[0].extension : "*70";
        return this.transfer(target);
    }

    async _engineCmd(name) {
        if (!this.engine || typeof this.engine[name] !== "function") {
            return false;
        }
        try {
            return await this.engine[name]();
        } catch {
            return false;
        }
    }

    /** Ferme le panneau post-appel. */
    dismissPostCall() {
        this.postCall = null;
    }

    _onBusIncomingCall(payload) {
        if (
            isDuplicateIncoming({
                state: this.state,
                currentCall: this.status.currentCall,
                payload,
            })
        ) {
            return;
        }
        this.notification.add(
            _t("Appel entrant de %(num)s", {num: payload.num || _t("inconnu")}),
            {type: "info"}
        );
    }

    /**
     * Notification bus « appel manqué » (émise par ``finalize_wazo_call``).
     *
     * @param {?Object} payload ``{num, name, partner_id, partner_name}``
     */
    _onBusMissedCall(payload) {
        if (isEmptyMissedNotice(payload)) {
            return;
        }
        const label = payload.partner_name || payload.name || payload.num;
        this.notification.add(
            _t("Appel manqué de %(label)s", {label: label || _t("inconnu")}),
            {type: "warning"}
        );
    }

    /**
     * @param {String} state
     * @param {String} message
     */
    _startRingtone() {
        try {
            this._startRingtoneUnsafe();
        } catch (e) {
            // Never let an audio failure break the call flow.
        }
    }

    _startRingtoneUnsafe() {
        if (this._ringAudio) {
            return;
        }
        // Real phone bell: generated ring.wav played on loop. The audio
        // element is unlocked by the first user click (see connect()).
        this._ringAudio = new Audio("/wazo_phone/static/src/audio/ring.wav");
        this._ringAudio.loop = true;
        // Safety: a notification-driven ring (call answered on another device)
        // never receives an "ended" event — auto-stop after 60 s.
        this._ringTimeout = setTimeout(() => this._stopRingtone(), 60000);
        const played = this._ringAudio.play();
        if (played && played.then) {
            played.catch(() => {
                this._ringAudio = null;
                this._startWebAudioRing();
            });
        }
    }

    _startWebAudioRing() {
        if (this._ringCtx) {
            this._ringCtx.resume().catch(() => {});
            return;
        }
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) {
            return;
        }
        // Web Audio ring: two-tone warble, no asset file needed.
        const ctx = this._audioCtx || new AC();
        this._audioCtx = ctx;
        if (ctx.state === "suspended") {
            ctx.resume().catch(() => {});
        }
        // Classic phone ring: dual tone (440+480 Hz) pulsing twice every 4 s.
        const osc1 = ctx.createOscillator();
        const osc2 = ctx.createOscillator();
        const gain = ctx.createGain();
        osc1.type = osc2.type = "sine";
        osc1.frequency.value = 440;
        osc2.frequency.value = 480;
        gain.gain.value = 0;
        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(ctx.destination);
        osc1.start();
        osc2.start();
        const pulse = () => {
            const t = ctx.currentTime;
            for (const off of [0, 0.4]) {
                gain.gain.setValueAtTime(0, t + off);
                gain.gain.linearRampToValueAtTime(0.15, t + off + 0.02);
                gain.gain.setValueAtTime(0.15, t + off + 0.25);
                gain.gain.linearRampToValueAtTime(0, t + off + 0.3);
            }
        };
        pulse();
        this._ringInterval = setInterval(pulse, 4000);
        this._ringCtx = ctx;
        this._ringNodes = {osc1, osc2, gain};
    }

    _stopRingtone() {
        if (this._ringTimeout) {
            clearTimeout(this._ringTimeout);
            this._ringTimeout = null;
        }
        if (this._ringAudio) {
            const a = this._ringAudio;
            this._ringAudio = null;
            a.pause();
            // load() aborts a still-pending play() — pause() alone can race
            // and the ring keeps playing after the call is answered.
            a.load();
        }
        if (this._ringInterval) {
            clearInterval(this._ringInterval);
            this._ringInterval = null;
        }
        if (this._ringCtx) {
            const {osc1, osc2} = this._ringNodes;
            osc1.stop();
            osc2.stop();
            this._ringCtx.close();
            this._ringCtx = null;
            this._ringNodes = null;
        }
    }

    _setState(state, message) {
        // Incoming-call ringtone: loop while ringing, stop on any other state.
        if (state === STATES.RINGING) {
            this._startRingtone();
        } else {
            this._stopRingtone();
        }
        this.status.state = state;
        this.status.message = message || "";
        this.bus.trigger("state_changed", {state, message});
        // Le propriétaire est la source de vérité : il diffuse l'état aux
        // autres onglets (le canal ne renvoie pas à l'émetteur).
        if (this.arbiter && this.arbiter.isLeader) {
            this.arbiter.publishState({state, message: this.status.message});
        }
    }

    _disposeSip() {
        const engine = this.engine;
        this.engine = null;
        if (engine) {
            // Volontairement non attendu : appelé aussi depuis
            // ``beforeunload``, où l'attente n'aurait pas le temps
            // d'aboutir.
            engine.stop();
        }
    }
}

export {STATES};

const wazoSoftphoneService = {
    dependencies: ["orm", "notification", "bus_service"],
    start(env, services) {
        const service = new WazoSoftphoneService(env, services);
        // Eagerly fetch the per-user config so isConfigured is settled by
        // the time any UI (systray, click-to-call) looks at it.
        service.loadConfig();
        // Start the multi-tab arbiter right away: without it no tab ever
        // becomes leader, shouldForward stays true, and callOut forwards
        // commands into a channel nobody listens on.
        service.connect();
        return service;
    },
};

registry.category("services").add("wazo_softphone", wazoSoftphoneService);

