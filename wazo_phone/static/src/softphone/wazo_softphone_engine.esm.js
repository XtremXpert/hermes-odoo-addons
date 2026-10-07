/**
 * Fabrique de moteur SIP (P3.3f).
 *
 * Le service softphone ne connaît **qu'une interface** : il reçoit un objet
 * moteur et lui parle (``start``, ``call``, ``answer``, ``hold``, ``sendDtmf``,
 * ``transfer``, ``stop``) sans savoir qui l'implémente. Deux moteurs la
 * respectent :
 *
 * * ``wazo_sdk`` — ``WebRTCClient`` du SDK officiel Wazo (**retenu**, P3.3f) ;
 * * ``sipjs``    — couche SIP.js écrite à la main (repli ; n'attache pas
 *   l'audio distant).
 *
 * Le choix vient du backend (``wazo.softphone_engine``, porté par la
 * configuration servie au navigateur) : c'est un paramètre, donc un
 * changement de moteur ne demande pas de redéploiement de code.
 *
 * Les globaux (``SIP``, ``WazoSDK``) et le magasin d'options sont injectés :
 * ce module est testable hors navigateur.
 */
// Imports avec extension explicite : le transpileur Odoo retire « .js »
// (``url_to_module_path``) et les normalise donc à l'identique des imports
// sans extension, tandis que Node — qui exige l'extension en ESM — peut
// résoudre ces modules et les tester hors navigateur.
import {SipJsEngine} from "./wazo_softphone_sipjs_engine.esm.js";
import {WazoSdkEngine} from "./wazo_softphone_sdk_engine.esm.js";

export const ENGINES = Object.freeze({
    WAZO_SDK: "wazo_sdk",
    SIPJS: "sipjs",
});

/** Moteur retenu (décision P3.3f) et valeur de repli. */
export const DEFAULT_ENGINE = ENGINES.WAZO_SDK;

/** Bundle d'assets (lazy-loadé) qui apporte le global de chaque moteur. */
export const ENGINE_BUNDLES = Object.freeze({
    [ENGINES.WAZO_SDK]: "wazo_phone.assets_sdk",
    [ENGINES.SIPJS]: "wazo_phone.assets_sip",
});

/** Nom du global attendu sur la page pour chaque moteur. */
export const ENGINE_GLOBALS = Object.freeze({
    [ENGINES.WAZO_SDK]: "WazoSDK",
    [ENGINES.SIPJS]: "SIP",
});

/**
 * Ramène un nom de moteur à une valeur connue.
 *
 * @param {?string} name
 * @returns {String}
 */
export function normalizeEngineName(name) {
    const value = typeof name === "string" ? name.trim() : "";
    return Object.values(ENGINES).includes(value) ? value : DEFAULT_ENGINE;
}

/**
 * @param {?string} name
 * @returns {String} nom du global attendu
 */
export function engineGlobalName(name) {
    return ENGINE_GLOBALS[normalizeEngineName(name)];
}

/**
 * @param {?string} name
 * @returns {String} nom du bundle d'assets à charger
 */
export function engineBundleName(name) {
    return ENGINE_BUNDLES[normalizeEngineName(name)];
}

/**
 * Le global du moteur est-il chargé ?
 *
 * @param {?string} name
 * @param {Object} [scope] portée où chercher le global (défaut : globale)
 * @returns {Boolean}
 */
export function isEngineLoaded(name, scope = globalThis) {
    return Boolean(scope && scope[engineGlobalName(name)]);
}

/**
 * Construit le moteur demandé.
 *
 * Le moteur est retourné même si son global est absent : c'est ``start()``
 * qui signale proprement l'indisponibilité (message utilisateur), plutôt
 * qu'une exception à la construction.
 *
 * @param {Object} options
 * @param {?string} options.name moteur demandé
 * @param {Object} options.config configuration softphone d'Odoo
 * @param {function} options.onEvent récepteur d'événements normalisés
 * @param {Object} [options.scope] portée des globaux (défaut : globale)
 * @param {Number} [options.dtmfDelayMs] délai entre touches (moteur SDK)
 * @returns {Object} moteur
 */
export function createEngine({
    name,
    config,
    onEvent,
    scope = globalThis,
    dtmfDelayMs,
} = {}) {
    const engine = normalizeEngineName(name);
    if (engine === ENGINES.SIPJS) {
        return new SipJsEngine({config, sip: scope?.SIP, onEvent});
    }
    return new WazoSdkEngine({
        config,
        sdk: scope?.WazoSDK,
        onEvent,
        dtmfDelayMs,
    });
}
