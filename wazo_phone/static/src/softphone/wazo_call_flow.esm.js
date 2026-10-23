/**
 * Logique de bouclage d'appel — fonctions pures, testables hors navigateur
 * (voir ``static/tests/wazo_call_flow.test.js``).
 *
 * Le service garde un ``currentCall`` normalisé pendant toute la session ;
 * ces fonctions couvrent sa construction, la charge utile envoyée à
 * ``res.users.finalize_wazo_call`` et la déduplication des notifications
 * d'appel entrant venues du bus Odoo (P3.3g) — la session qui a relayé
 * l'appel reçoit sa propre notification en retour et ne doit pas sonner une
 * seconde fois.
 */

/**
 * Construit la fiche de l'appel courant.
 *
 * @param {Object} params
 * @param {String} params.direction ``inbound`` | ``outbound`` | ``internal``
 * @param {String} params.num l'autre partie (numéro ou poste)
 * @param {String} [params.name] nom affiché de l'autre partie
 * @param {Number} [params.startedAt] horodatage ms (``Date.now()``)
 * @returns {Object}
 */
export function buildCallInfo({direction, num, name = "", startedAt = Date.now()}) {
    return {
        direction: direction || "outbound",
        num: String(num || ""),
        name: String(name || ""),
        answered: false,
        startedAt,
    };
}

/**
 * Charge utile de ``res.users.finalize_wazo_call``.
 *
 * @param {?Object} call fiche construite par ``buildCallInfo``
 * @param {Number} [endedAt] horodatage ms de fin (défaut : maintenant)
 * @returns {?Object} ``null`` sans appel à consigner
 */
export function finalizePayload(call, endedAt = Date.now()) {
    if (!call || !call.num) {
        return null;
    }
    return {
        num: call.num,
        name: call.name || "",
        direction: call.direction || "outbound",
        answered: Boolean(call.answered),
        // Durée approximative côté navigateur : le CDR Wazo fera foi à la
        // synchronisation — ici la note du contact veut un ordre de grandeur.
        duration: Math.max(Math.round((endedAt - call.startedAt) / 1000), 0),
    };
}

/**
 * La notification bus « appel entrant » doit-elle être ignorée ?
 *
 * Chaque session de l'utilisateur reçoit la notification émise par
 * ``notify_wazo_incoming_call`` — y compris l'onglet qui l'a relayée. Si la
 * session sonne déjà (couche SIP ou canal inter-onglets), ou qu'un appel
 * est en cours, la notification est une redite : on l'ignore.
 *
 * @param {Object} params
 * @param {String} params.state état courant du service
 * @param {?Object} params.currentCall fiche de l'appel suivi
 * @param {?Object} params.payload notification bus
 * @returns {Boolean}
 */
export function isDuplicateIncoming({state, currentCall, payload}) {
    if (!payload) {
        return true;
    }
    if (state === "ringing" || state === "in_call" || state === "outbound") {
        return true;
    }
    const num = String(payload.num || "");
    if (currentCall && currentCall.num && num && currentCall.num === num) {
        return true;
    }
    return false;
}

/**
 * La notification bus « appel manqué » doit-elle être ignorée ?
 *
 * Contrairement à l'appel entrant, l'appel manqué intéresse aussi la
 * session qui l'a signalé (elle vient de raccrocher) : on n'ignore que les
 * charges vides.
 *
 * @param {?Object} payload
 * @returns {Boolean}
 */
export function isEmptyMissedNotice(payload) {
    return !payload || (!payload.num && !payload.name);
}
