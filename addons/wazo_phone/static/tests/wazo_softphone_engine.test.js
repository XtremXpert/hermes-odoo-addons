/**
 * Tests de la fabrique de moteur SIP (P3.3f).
 *
 * La fabrique est le seul endroit qui sait **quel** moteur existe et **où**
 * se trouve son global. Le service, lui, ne connaît qu'une interface. Ces
 * tests vérifient donc :
 *
 * * la normalisation du nom (une valeur inconnue ne doit jamais produire un
 *   softphone sans moteur) ;
 * * le couple global / bundle d'assets attendu par moteur ;
 * * la sélection effective et l'injection des globaux.
 *
 * Exécution : `node --test wazo_phone/static/tests/`
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
    DEFAULT_ENGINE,
    ENGINES,
    createEngine,
    engineBundleName,
    engineGlobalName,
    isEngineLoaded,
    normalizeEngineName,
} from "../src/softphone/wazo_softphone_engine.js";
import { SipJsEngine } from "../src/softphone/wazo_softphone_sipjs_engine.js";
import { WazoSdkEngine } from "../src/softphone/wazo_softphone_sdk_engine.js";

const CONFIG = {
    enabled: true,
    ws_url: "wss://wazo-test.636.vezina.biz/api/asterisk/ws",
    aor: "m0kxsfvz",
    auth_user: "1011",
    auth_password: "secret-1011",
    domain: "asterisk",
    display_name: "Alice Dupont",
    extension: "1011",
};

// ─── Normalisation ───────────────────────────────────────────────────────────

test("le moteur retenu est celui du SDK officiel", () => {
    assert.equal(DEFAULT_ENGINE, ENGINES.WAZO_SDK);
});

test("les noms de moteurs connus sont conservés", () => {
    assert.equal(normalizeEngineName("wazo_sdk"), ENGINES.WAZO_SDK);
    assert.equal(normalizeEngineName("sipjs"), ENGINES.SIPJS);
    assert.equal(normalizeEngineName("  sipjs  "), ENGINES.SIPJS);
});

test("une valeur absente ou inconnue retombe sur le moteur retenu", () => {
    // Un softphone sans moteur serait un softphone muet : jamais de « rien ».
    for (const value of ["", "  ", "moteur-imaginaire", null, undefined, 42, {}]) {
        assert.equal(normalizeEngineName(value), DEFAULT_ENGINE, `valeur : ${value}`);
    }
});

test("chaque moteur annonce son global et son bundle d'assets", () => {
    assert.equal(engineGlobalName(ENGINES.WAZO_SDK), "WazoSDK");
    assert.equal(engineGlobalName(ENGINES.SIPJS), "SIP");
    assert.equal(engineBundleName(ENGINES.WAZO_SDK), "wazo_phone.assets_sdk");
    assert.equal(engineBundleName(ENGINES.SIPJS), "wazo_phone.assets_sip");
    // Un nom inconnu décrit le moteur retenu.
    assert.equal(engineGlobalName("n_importe_quoi"), "WazoSDK");
    assert.equal(engineBundleName("n_importe_quoi"), "wazo_phone.assets_sdk");
});

test("le global attendu est cherché dans la portée fournie", () => {
    assert.equal(isEngineLoaded(ENGINES.SIPJS, { SIP: {} }), true);
    assert.equal(isEngineLoaded(ENGINES.SIPJS, { WazoSDK: {} }), false);
    assert.equal(isEngineLoaded(ENGINES.WAZO_SDK, { WazoSDK: {} }), true);
    assert.equal(isEngineLoaded(ENGINES.WAZO_SDK, null), false);
});

// ─── Sélection ───────────────────────────────────────────────────────────────

test("le moteur demandé est celui qui est construit", () => {
    const sdk = createEngine({ name: ENGINES.WAZO_SDK, config: CONFIG, onEvent: () => {} });
    const sipjs = createEngine({ name: ENGINES.SIPJS, config: CONFIG, onEvent: () => {} });
    assert.ok(sdk instanceof WazoSdkEngine);
    assert.ok(sipjs instanceof SipJsEngine);
});

test("sans nom de moteur, c'est le SDK qui est construit", () => {
    const engine = createEngine({ config: CONFIG, onEvent: () => {} });
    assert.ok(engine instanceof WazoSdkEngine);
});

test("les globaux sont pris dans la portée et injectés dans le moteur", () => {
    const fakeSdk = { WebRTCClient: class {} };
    const fakeSip = { UserAgent: class {} };
    const sdk = createEngine({
        name: ENGINES.WAZO_SDK,
        config: CONFIG,
        onEvent: () => {},
        scope: { WazoSDK: fakeSdk, SIP: fakeSip },
    });
    const sipjs = createEngine({
        name: ENGINES.SIPJS,
        config: CONFIG,
        onEvent: () => {},
        scope: { WazoSDK: fakeSdk, SIP: fakeSip },
    });
    assert.equal(sdk.sdk, fakeSdk);
    assert.equal(sipjs.sip, fakeSip);
});

test("un moteur est construit même si son global manque : c'est start() qui le dit", async () => {
    // La fabrique ne doit pas lever : l'utilisateur doit lire un message,
    // pas une exception de construction.
    const events = [];
    const engine = createEngine({
        name: ENGINES.WAZO_SDK,
        config: CONFIG,
        onEvent: (type, payload) => events.push([type, payload]),
        scope: {},
    });
    assert.ok(engine instanceof WazoSdkEngine);
    assert.equal(await engine.start(), false);
    assert.deepEqual(events, [["error", { message: "SDK Wazo indisponible." }]]);
});
