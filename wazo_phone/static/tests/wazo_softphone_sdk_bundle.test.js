/**
 * Test de l'artefact vendorisé @wazo/sdk (P3.3f).
 *
 * Ce fichier ne teste pas du code que nous écrivons : il teste **ce que
 * nous livrons**. Le bundle UMD officiel est vendorisé puis enveloppé dans
 * une IIFE ; si quelqu'un le remplace par une version brute, ou si la
 * régénération casse l'enveloppe, ce test doit le dire.
 *
 * Exécution : `node --test wazo_phone/static/tests/`
 */
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";

const BUNDLE = new URL("../../static/lib/wazo-sdk.js", import.meta.url);
const SOURCE = readFileSync(BUNDLE, "utf8");

/** Charge le bundle dans un faux objet global et retourne cet objet. */
function loadBundle() {
    const root = {
        window: {},
        navigator: {userAgent: "node"},
        document: undefined,
    };
    root.globalThis = root;
    // Le bundle est un script classique (pas un module ES) : on l'exécute
    // avec un objet global maîtrisé, comme le ferait le navigateur.
    const run = new Function("globalThis", SOURCE);
    run(root);
    return root;
}

test("le bundle vendorisé expose l'API du SDK sous un seul nom global", () => {
    const root = loadBundle();
    assert.equal(typeof root.WazoSDK, "object", "window.WazoSDK attendu");
    assert.equal(
        typeof root.WazoSDK.WebRTCClient,
        "function",
        "WebRTCClient est le client WebRTC du SDK (moteur SIP alternatif)"
    );
    // Le SDK publie une soixantaine d'exports ; on vérifie quelques-uns de
    // ceux sur lesquels le moteur s'appuiera.
    for (const name of ["CallSession", "Session", "Incall", "Line"]) {
        assert.ok(name in root.WazoSDK, `export ${name} attendu dans window.WazoSDK`);
    }
});

test("le bundle n'étale PAS ses exports sur la racine", () => {
    // C'est la raison d'être de l'enveloppe : le repli du UMD fait
    // ``root[i] = a[i]`` pour chacun de ses 66 exports, ce qui définirait
    // window.Session, window.Contact, window.Line… dans la page Odoo —
    // des noms suffisamment génériques pour heurter autre chose.
    const root = loadBundle();
    const polluted = ["Session", "Contact", "Profile", "Line", "Call"].filter(
        (name) => name in root
    );
    assert.deepEqual(
        polluted,
        [],
        "aucun export ne doit atterrir hors de window.WazoSDK"
    );
});

test("le bundle n'expose pas de global 'SIP' concurrent", () => {
    // Le SDK embarque sip.js 0.21.2 en interne (la MÊME version que notre
    // bundle SIP.js vendorisé). S'il exposait un global ``SIP``, les deux
    // moteurs se marcheraient dessus.
    const root = loadBundle();
    assert.equal(root.SIP, undefined, "le SDK ne doit pas définir window.SIP");
});

test("le bundle embarque sip.js 0.21.2 (même version que le nôtre)", () => {
    // Fait de décision de P3.3f : le SDK n'est pas un fork de SIP.js, il
    // dépend de la version que nous vendorisons déjà. Si cette version
    // change, la comparaison « SIP.js vs SDK » doit être rejouée.
    assert.match(
        SOURCE,
        /sip\.js v?0\.21\.2|SIP\.js\/0\.21\.2|"0\.21\.2"/,
        "sip.js 0.21.2 attendu dans le bundle"
    );
});
