/**
 * Tests du moteur SIP adossé au SDK Wazo (P3.3f).
 *
 * Le SDK est **injecté** : on lui substitue un double qui enregistre les
 * appels reçus et sait émettre les événements. Ce qui est vérifié ici n'est
 * pas le SDK (il est fourni par Wazo), c'est **notre traduction** :
 *
 * * la configuration transmise (hôte/port, et surtout l'AOR en
 *   ``authorizationUser`` — piège P3.2) ;
 * * la table de correspondance des événements (transport vs appel) ;
 * * le découpage DTMF (le SDK ne prend qu'une touche à la fois) ;
 * * la tolérance aux commandes sans session.
 *
 * Exécution : `node --test wazo_phone/static/tests/`
 */
import assert from "node:assert/strict";
import {test} from "node:test";

import {
    SDK_EVENTS,
    WazoSdkEngine,
    parseWssUrl,
    sdkConfigFrom,
} from "../src/softphone/wazo_softphone_sdk_engine.esm.js";

/** Configuration softphone telle que servie par Odoo. */
const CONFIG = {
    enabled: true,
    ws_url: "wss://wazo-test.636.vezina.biz/api/asterisk/ws",
    aor: "m0kxsfvz",
    auth_user: "1011",
    auth_password: "secret-1011",
    domain: "wazo-test.636.vezina.biz",
    display_name: "Alice Dupont",
    extension: "1011",
};

/** Double du ``WebRTCClient`` du SDK. */
class FakeWebRTCClient {
    constructor(options) {
        this.options = options;
        this.handlers = new Map();
        this.calls = [];
        FakeWebRTCClient.last = this;
    }

    on(event, handler) {
        if (!this.handlers.has(event)) {
            this.handlers.set(event, []);
        }
        this.handlers.get(event).push(handler);
    }

    emit(event, ...args) {
        for (const handler of this.handlers.get(event) || []) {
            handler(...args);
        }
    }

    async waitForRegister() {
        this.calls.push(["waitForRegister"]);
    }

    async close(force) {
        this.calls.push(["close", force]);
    }

    call(...args) {
        this.calls.push(["call", ...args]);
        return {id: "sess-out"};
    }

    async answer(session) {
        this.calls.push(["answer", session]);
    }

    async hangup(session) {
        this.calls.push(["hangup", session]);
    }

    async hold(session) {
        this.calls.push(["hold", session]);
    }

    async unhold(session) {
        this.calls.push(["unhold", session]);
    }

    sendDTMF(session, tone) {
        this.calls.push(["sendDTMF", tone]);
        return true;
    }

    transfer(session, target) {
        this.calls.push(["transfer", target]);
    }

    getNumber() {
        return "2000";
    }
}

const FAKE_SDK = {WebRTCClient: FakeWebRTCClient};

/** Installe un moteur avec un SDK factice et collecte les événements. */
async function makeEngine({config = CONFIG, sdk = FAKE_SDK, start = true} = {}) {
    const events = [];
    const engine = new WazoSdkEngine({
        config,
        sdk,
        dtmfDelayMs: 0,
        onEvent: (type, payload) => events.push([type, payload]),
    });
    if (start) {
        await engine.start();
    }
    return {engine, events, client: FakeWebRTCClient.last};
}

// ─── Traduction de la configuration ──────────────────────────────────────────

test("l'hôte et le port sont extraits de l'URL WebSocket", () => {
    assert.deepEqual(parseWssUrl("wss://wazo-test.636.vezina.biz/api/asterisk/ws"), {
        host: "wazo-test.636.vezina.biz",
        port: 443,
    });
    assert.deepEqual(parseWssUrl("wss://hote.example:8443/api/asterisk/ws"), {
        host: "hote.example",
        port: 8443,
    });
    assert.deepEqual(parseWssUrl("ws://hote.example/api/asterisk/ws"), {
        host: "hote.example",
        port: 80,
    });
    assert.equal(parseWssUrl(""), null);
    assert.equal(parseWssUrl(undefined), null);
    assert.equal(parseWssUrl("n'importe quoi"), null);
});

test("la configuration du SDK reçoit un hôte/port, jamais une URL complète", () => {
    // Le SDK reconstruit lui-même « wss://<hôte>:<port>/api/asterisk/ws ».
    // Lui passer une URL complète dans ``websocketSip`` le casserait : il la
    // découpe sur « : » et prendrait « wss » pour un hôte, NaN pour un port.
    const options = sdkConfigFrom(CONFIG);
    assert.equal(options.host, "wazo-test.636.vezina.biz");
    assert.equal(options.port, 443);
    assert.equal(options.websocketSip, undefined);
    assert.equal(options.uri, undefined, "l'URI est construite par le SDK");
    assert.deepEqual(options.media, {audio: true});
});

test("l'AOR (nom d'endpoint) est passé comme identité, pas l'extension", () => {
    // Piège P3.2 : pour un endpoint généré par Wazo, le From/AOR est le nom
    // de l'endpoint (m0kxsfvz), pas l'extension (1011). Le SDK dérive l'URI
    // de ``authorizationUser`` : lui donner l'extension produirait un From
    // que Wazo ne reconnaît pas.
    const options = sdkConfigFrom(CONFIG);
    assert.equal(options.authorizationUser, "m0kxsfvz");
    assert.notEqual(options.authorizationUser, CONFIG.auth_user);
    assert.equal(options.password, "secret-1011");
});

test("sans URL WebSocket, le domaine SIP sert de repli", () => {
    const options = sdkConfigFrom({...CONFIG, ws_url: ""});
    assert.equal(options.host, "wazo-test.636.vezina.biz");
    assert.equal(options.port, 443);
});

// ─── Cycle de vie ────────────────────────────────────────────────────────────

test("démarrer construit le client avec la configuration et attend l'enregistrement", async () => {
    const {engine, client} = await makeEngine();
    assert.equal(client.options.host, "wazo-test.636.vezina.biz");
    assert.equal(client.options.authorizationUser, "m0kxsfvz");
    assert.deepEqual(client.calls, [["waitForRegister"]]);
    assert.equal(engine.hasSession, false);
});

test("un SDK absent est signalé sans lever d'exception", async () => {
    const {engine, events} = await makeEngine({sdk: {}, start: true});
    assert.deepEqual(
        events.map(([type]) => type),
        ["error"]
    );
    await engine.call("2000");
    assert.equal(engine.hasSession, false);
});

test("un échec d'enregistrement est signalé comme erreur", async () => {
    class FailingClient extends FakeWebRTCClient {
        async waitForRegister() {
            throw new Error("401 Unauthorized");
        }
    }
    const {engine, events} = await makeEngine({
        sdk: {WebRTCClient: FailingClient},
    });
    assert.deepEqual(events, [["error", {message: "401 Unauthorized"}]]);
    assert.equal(engine.client instanceof FailingClient, true);
});

test("l'événement d'enregistrement du SDK est relayé", async () => {
    const {events, client} = await makeEngine();
    client.emit(SDK_EVENTS.REGISTERED);
    client.emit(SDK_EVENTS.UNREGISTERED);
    assert.deepEqual(
        events.map(([type]) => type),
        ["registered", "unregistered"]
    );
});

test("arrêter ferme le client", async () => {
    const {engine, client} = await makeEngine();
    await engine.stop();
    assert.deepEqual(client.calls, [["waitForRegister"], ["close", true]]);
    assert.equal(engine.client, null);
});

// ─── Appels ──────────────────────────────────────────────────────────────────

test("un appel entrant est relayé avec le numéro de l'appelant", async () => {
    const {engine, events, client} = await makeEngine();
    const session = {id: "sess-in"};
    client.emit(SDK_EVENTS.INVITE, session);
    assert.deepEqual(events, [["incoming", {from: "2000", name: ""}]]);
    assert.equal(engine.sessionId, "sess-in");
});

test("répondre passe la session au SDK", async () => {
    const {engine, client} = await makeEngine();
    const session = {id: "sess-in"};
    client.emit(SDK_EVENTS.INVITE, session);
    assert.equal(await engine.answer(), true);
    assert.deepEqual(client.calls.at(-1), ["answer", session]);
});

test("un appel sortant suit le contrat audio-only du SDK", async () => {
    const {engine, client} = await makeEngine();
    assert.equal(await engine.call("2000"), true);
    // Call(number, enableVideo, audioOnly, conference, options)
    assert.deepEqual(client.calls.at(-1), ["call", "2000", false, true, false, {}]);
    assert.equal(engine.sessionId, "sess-out");
});

test("l'appel établi (ACCEPTED) est distingué du transport (CONNECTED)", async () => {
    // CONNECTED/DISCONNECTED sont des événements de transport : les confondre
    // avec l'état d'appel ferait croire à une conversation dès l'ouverture du
    // WebSocket.
    const {events, client} = await makeEngine();
    client.emit(SDK_EVENTS.CONNECTED);
    assert.deepEqual(events, [], "le transport seul n'est pas un appel");
    client.emit(SDK_EVENTS.ACCEPTED, {id: "sess-out"});
    assert.deepEqual(
        events.map(([type]) => type),
        ["in_call"]
    );
});

test("une perte de transport est signalée comme telle", async () => {
    const {events, client} = await makeEngine();
    client.emit(SDK_EVENTS.TRANSPORT_ERROR, new Error("boom"));
    client.emit(SDK_EVENTS.DISCONNECTED, new Error("bye"));
    assert.deepEqual(
        events.map(([type]) => type),
        ["transport_lost", "transport_lost"]
    );
});

test("raccrocher termine la session puis la libère", async () => {
    const {engine, client} = await makeEngine();
    client.emit(SDK_EVENTS.INVITE, {id: "sess-in"});
    await engine.hangup();
    assert.equal(client.calls.at(-1)[0], "hangup");
    assert.equal(engine.hasSession, false);
    assert.equal(engine.sessionId, null);
});

test("la fin d'appel distante libère la session", async () => {
    const {engine, events, client} = await makeEngine();
    let listener = null;
    client.emit(SDK_EVENTS.INVITE, {
        id: "sess-in",
        stateChange: {addListener: (cb) => (listener = cb)},
    });
    assert.equal(engine.hasSession, true);
    listener({newState: "Terminated"});
    assert.equal(engine.hasSession, false);
    assert.deepEqual(events.at(-1), ["ended", undefined]);
});

// ─── Cœur d'appel ────────────────────────────────────────────────────────────

test("une séquence DTMF est découpée touche par touche", async () => {
    // ``WebRTCClient.sendDTMF`` ne prend qu'UNE touche : lui passer « 12* »
    // d'un bloc ne composerait rien.
    const {engine, client} = await makeEngine();
    client.emit(SDK_EVENTS.INVITE, {id: "sess-in"});
    assert.equal(await engine.sendDtmf("12*"), true);
    const tones = client.calls
        .filter(([name]) => name === "sendDTMF")
        .map(([, tone]) => tone);
    assert.deepEqual(tones, ["1", "2", "*"]);
});

test("hold, unhold et transfert visent la session courante", async () => {
    const {engine, client} = await makeEngine();
    const session = {id: "sess-in"};
    client.emit(SDK_EVENTS.INVITE, session);
    await engine.hold();
    await engine.unhold();
    await engine.transfer("3000");
    assert.deepEqual(client.calls.slice(-3), [
        ["hold", session],
        ["unhold", session],
        ["transfer", "3000"],
    ]);
});

test("les commandes sans session ne font rien et ne lèvent pas", async () => {
    const {engine, client} = await makeEngine();
    const before = client.calls.length;
    assert.equal(await engine.answer(), false);
    assert.equal(await engine.hangup(), false);
    assert.equal(await engine.hold(), false);
    assert.equal(await engine.unhold(), false);
    assert.equal(await engine.sendDtmf("1"), false);
    assert.equal(await engine.transfer("3000"), false);
    assert.equal(client.calls.length, before, "aucun appel SDK attendu");
});

test("un échec de commande devient une erreur signalée", async () => {
    class FailingHold extends FakeWebRTCClient {
        async hold() {
            throw new Error("re-INVITE refusé");
        }
    }
    const events = [];
    const engine = new WazoSdkEngine({
        config: CONFIG,
        sdk: {WebRTCClient: FailingHold},
        dtmfDelayMs: 0,
        onEvent: (type, payload) => events.push([type, payload]),
    });
    await engine.start();
    engine.session = {id: "sess-in"};
    assert.equal(await engine.hold(), false);
    assert.deepEqual(events.at(-1), ["error", {message: "re-INVITE refusé"}]);
});
