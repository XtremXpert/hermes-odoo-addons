/**
 * Arbitrage multi-onglets du softphone (P3.3e).
 *
 * **Le problème est côté navigateur.** Avec N onglets Odoo ouverts, chaque
 * onglet instancie son propre ``UserAgent``/``Registerer`` SIP.js : N
 * enregistrements SIP, N sonneries pour un seul appel, double décroché
 * possible, états divergents. Rien de tout cela ne se règle sur Wazo — le
 * PBX voit simplement N contacts.
 *
 * **La solution.** Un verrou exclusif (``navigator.locks``, Web Locks API)
 * désigne UN onglet propriétaire : lui seul construit la couche SIP et
 * s'enregistre. Un canal de diffusion (``BroadcastChannel``) porte l'état
 * entre onglets, et un arbitrage de revendication (« claimed ») départage
 * qui décroche.
 *
 * **Propriété de la couche SIP ≠ propriété de l'appel.** Le verrou
 * appartient à l'onglet qui enregistre ; l'appel, lui, appartient à
 * l'onglet qui décroche. Les autres onglets sont des **télécommandes** :
 * leurs commandes (hold, DTMF, transfert, raccrocher) remontent au
 * propriétaire, qui les exécute sur la session.
 *
 * **Le verrou rendu revient au suivant.** Quand l'onglet propriétaire se
 * ferme, le verrou passe à l'onglet en attente : ``onLeadership`` le
 * prévient pour qu'il démarre SA couche SIP. Sans cette reprise, fermer un
 * onglet rendrait le téléphone muet.
 *
 * Les adaptateurs sont **injectés** (``locks``, ``createChannel``) afin que
 * la logique soit testable hors navigateur — voir
 * ``static/tests/wazo_softphone_arbiter.test.js``.
 */

/** Nom du verrou exclusif partagé par tous les onglets d'un poste. */
export const LEADER_LOCK = "wazo_softphone_leader";

/** Nom du canal de diffusion inter-onglets. */
export const CHANNEL_NAME = "wazo_softphone";

/** Types de messages échangés entre onglets. */
export const MSG = Object.freeze({
    /** Un onglet devient propriétaire de la couche SIP. */
    LEADER: "leader",
    /** Un onglet revendique l'appel courant (il décroche). */
    CLAIM: "claim",
    /** Fin d'appel : la revendication est libérée partout. */
    RELEASE: "release",
    /** Appel entrant, diffusé par le propriétaire pour faire sonner tous les onglets. */
    INCOMING: "incoming",
    /** État de session diffusé par le propriétaire. */
    STATE: "state",
    /** Commande d'un onglet télécommande destinée au propriétaire. */
    COMMAND: "command",
    /** Un onglet se retire. */
    DETACH: "detach",
});

export class SoftphoneArbiter {
    /**
     * @param {Object} options
     * @param {String} options.tabId identifiant de cet onglet
     * @param {?object} [options.locks] gestionnaire de verrous (``navigator.locks``)
     * @param {?Function} [options.createChannel] fabrique du canal de diffusion
     */
    constructor({tabId, locks = null, createChannel = null} = {}) {
        this.tabId = tabId || `tab-${Math.random().toString(36).slice(2, 10)}`;
        this.locks = locks;
        this.createChannel = createChannel;
        /** @type {?object} */
        this.channel = null;
        /** @type {Boolean} cet onglet détient-il la couche SIP ? */
        this.leader = false;
        /** @type {?string} onglet propriétaire connu */
        this.leaderId = null;
        /** @type {?string} onglet ayant revendiqué l'appel */
        this.claimedBy = null;
        /** @type {?object} appel entrant en cours (tous les onglets) */
        this.incoming = null;
        /** @type {?Function} (bool) : démarrer/arrêter la couche SIP */
        this.onLeadership = null;
        /** @type {?Function} appel entrant relayé (onglets non propriétaires) */
        this.onIncoming = null;
        /** @type {?Function} propriétaire : exécute une commande télécommandée */
        this.onCommand = null;
        /** @type {?Function} télécommande : reflète l'état de session */
        this.onState = null;
        this._stopped = false;
        this._released = null;
    }

    // ─── Propriété de la couche SIP ──────────────────────────────────────────

    /** @returns {Boolean} */
    get isLeader() {
        return this.leader;
    }

    /** Seul le propriétaire construit ``UserAgent`` + ``Registerer``. */
    get shouldRegister() {
        return this.leader;
    }

    /** Un non-propriétaire doit relayer ses commandes au propriétaire. */
    get shouldForward() {
        return !this.leader;
    }

    /** @returns {Boolean} cet onglet est-il maître de l'appel ? */
    get isOwner() {
        return this.claimedBy === this.tabId;
    }

    /**
     * Démarre l'arbitrage : ouvre le canal et demande le verrou exclusif.
     *
     * **Ne pas attendre cette promesse pour savoir si l'on est
     * propriétaire** : elle ne se résout qu'à la libération du verrou.
     * Lire ``isLeader`` juste après l'appel (la désignation est synchrone
     * quand le verrou est libre) et s'abonner à ``onLeadership`` pour la
     * reprise ultérieure.
     *
     * @returns {Promise<void>}
     */
    async start() {
        this._stopped = false;
        this._openChannel();
        if (!this.locks || typeof this.locks.request !== "function") {
            // Repli (navigateur sans Web Locks, contexte non sécurisé) :
            // l'onglet se comporte comme seul au monde. Le softphone
            // fonctionne, seul l'arbitrage multi-onglets est perdu.
            this._becomeLeader();
            return;
        }
        return this._acquireLeadership();
    }

    /**
     * Arrête l'arbitrage et rend le verrou (le successeur prend la main).
     */
    stop() {
        this._stopped = true;
        this._post({type: MSG.DETACH, tabId: this.tabId});
        this._loseLeadership();
        this._releaseLock();
        this._closeChannel();
    }

    _acquireLeadership() {
        return this.locks
            .request(LEADER_LOCK, {mode: "exclusive"}, () => {
                if (this._stopped) {
                    return undefined;
                }
                this._becomeLeader();
                // Le verrou reste tenu tant que cette promesse n'est pas
                // résolue : c'est notre poignée pour le rendre (stop()).
                return new Promise((resolve) => {
                    this._released = resolve;
                });
            })
            .then(() => {
                this._loseLeadership();
                this._released = null;
                if (!this._stopped) {
                    // On a rendu le verrou sans s'arrêter : on reprend place
                    // dans la file (rechargement d'onglet, vol de verrou).
                    return this._acquireLeadership();
                }
            });
    }

    _becomeLeader() {
        if (this.leader) {
            return;
        }
        this.leader = true;
        this.leaderId = this.tabId;
        this._post({type: MSG.LEADER, tabId: this.tabId});
        if (this.onLeadership) {
            this.onLeadership(true);
        }
    }

    _loseLeadership() {
        if (!this.leader) {
            return;
        }
        this.leader = false;
        if (this.onLeadership) {
            this.onLeadership(false);
        }
    }

    _releaseLock() {
        const release = this._released;
        this._released = null;
        if (release) {
            release();
        }
    }

    // ─── Revendication de l'appel ────────────────────────────────────────────

    /**
     * Revendique l'appel courant pour cet onglet (il décroche).
     *
     * @returns {Boolean} ``false`` si un autre onglet l'a déjà revendiqué.
     */
    claim() {
        if (this.claimedBy !== null && this.claimedBy !== this.tabId) {
            return false;
        }
        this.claimedBy = this.tabId;
        this._post({type: MSG.CLAIM, tabId: this.tabId});
        return true;
    }

    /** Libère la revendication (fin d'appel) dans tous les onglets. */
    release() {
        this._post({type: MSG.RELEASE, tabId: this.tabId});
        this.claimedBy = null;
        this.incoming = null;
    }

    // ─── Diffusion d'état et de commandes ────────────────────────────────────

    /**
     * Diffuse l'appel entrant : tous les onglets sonnent (et l'un décrochera).
     *
     * @param {Object} info
     */
    broadcastIncoming(info) {
        this.incoming = info || null;
        this._post({type: MSG.INCOMING, payload: this.incoming});
    }

    /**
     * Diffuse l'état de session (propriétaire → télécommandes).
     *
     * @param {Object} state
     */
    publishState(state) {
        this._post({type: MSG.STATE, payload: state});
    }

    /**
     * Relaie une commande au propriétaire (hold, DTMF, transfert…).
     *
     * @param {String} name
     * @param {Object} [payload]
     */
    forwardCommand(name, payload) {
        this._post({type: MSG.COMMAND, payload: {name, payload}});
    }

    // ─── Réception ───────────────────────────────────────────────────────────

    /**
     * Traite un message d'un autre onglet.
     *
     * Tolérant par construction : un message illisible, tronqué ou étranger
     * est ignoré. Un onglet ne doit jamais casser son état d'appel parce
     * qu'un homologue a émis quelque chose d'inattendu.
     *
     * @param {*} message
     */
    handleMessage(message) {
        if (!message || typeof message !== "object") {
            return;
        }
        switch (message.type) {
            case MSG.LEADER:
                if (message.tabId) {
                    this.leaderId = message.tabId;
                }
                break;
            case MSG.CLAIM: {
                const other = message.tabId;
                if (!other) {
                    return;
                }
                if (this.claimedBy === null) {
                    this.claimedBy = other;
                } else if (this.claimedBy === this.tabId && other < this.tabId) {
                    // Revendications simultanées : on tranche par
                    // identifiant d'onglet, pour que tous les onglets
                    // désignent le même gagnant (sinon double décroché).
                    this.claimedBy = other;
                }
                break;
            }
            case MSG.RELEASE:
                this.claimedBy = null;
                this.incoming = null;
                break;
            case MSG.INCOMING:
                this.incoming = message.payload || null;
                if (this.onIncoming) {
                    this.onIncoming(this.incoming);
                }
                break;
            case MSG.STATE:
                if (this.onState) {
                    this.onState(message.payload);
                }
                break;
            case MSG.COMMAND: {
                const command = message.payload || {};
                if (this.onCommand) {
                    this.onCommand(command.name, command.payload);
                }
                break;
            }
            case MSG.DETACH:
                // Le partant emporte sa revendication, mais PAS l'appel
                // entrant : l'appel vit côté Wazo, il doit survivre à la
                // fermeture d'un onglet.
                if (message.tabId && this.claimedBy === message.tabId) {
                    this.claimedBy = null;
                }
                if (this.leaderId === message.tabId) {
                    this.leaderId = null;
                }
                break;
            default:
                break;
        }
    }

    // ─── Internes ────────────────────────────────────────────────────────────

    _openChannel() {
        if (this.channel || !this.createChannel) {
            return;
        }
        try {
            this.channel = this.createChannel(CHANNEL_NAME);
        } catch {
            this.channel = null;
            return;
        }
        if (this.channel) {
            this.channel.onmessage = (event) => this.handleMessage(event?.data);
        }
    }

    _closeChannel() {
        if (!this.channel) {
            return;
        }
        this.channel.onmessage = null;
        if (typeof this.channel.close === "function") {
            try {
                this.channel.close();
            } catch {
                // Ignore
            }
        }
        this.channel = null;
    }

    /**
     * @param {Object} message
     */
    _post(message) {
        if (!this.channel || this.channel.closed) {
            return;
        }
        try {
            this.channel.postMessage(message);
        } catch {
            // Ignore : la perte d'un message d'arbitrage ne doit jamais
            // interrompre un appel.
        }
    }
}
