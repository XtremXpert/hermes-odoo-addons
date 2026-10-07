/**
 * Tests du moteur « SIP.js écrit à la main » (P3.3f).
 *
 * Le global ``SIP`` est injecté : on lui substitue des doubles fidèles
 * (UserAgent, Registerer, Inviter) qui enregistrent ce qu'on leur demande.
 * Ce qui est testé ici est notre **câblage** :
 *
 * * ce qui part dans la configuration du UserAgent (et surtout l'AOR en
 *   ``uri`` contre l'extension en ``authorizationUsername`` — P3.2) ;
 * * la distinction entre enregistrement réussi / refusé (401) ;
 * * le cycle d'appel (invite, établi, terminé) ;
 * * le DTMF en une seule fois (SIP.js accepte la séquence, contrairement
 *   au SDK) ;
 * * la robustesse : ni exception ni appel au réseau quand il n'y a pas de
 *   session.
 *
 * Exécution : `node --test wazo_phone/static/tests/`
 */
import assert from "node:assert/strict";
import {test} from "node:test";

import {SipJsEngine} from "../src/softphone/wazo_softphone_sipjs_engine.esm.js";

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

/** Double du UserAgent de SIP.js. */
class FakeUserAgent {
    static instances = [];
    static failStart = null;
    static uris = [];

    static makeURI(value) {
        FakeUserAgent.uris.push(value);
        return {value};
    }

    constructor(options) {
        this.options = options;
        this.started = false;
        this.stopped = false;
        this.reconnects = 0;
        FakeUserAgent.instances.push(this);
    }

    async start() {
        if (FakeUserAgent.failStart) {
            throw new Error(FakeUserAgent.failStart);
        }
        this.started = true;
    }

    stop() {
        this.stopped = true;
    }

    reconnect() {
        this.reconnects += 1;
    }
}

/** Double du Registerer de SIP.js. */
class FakeRegisterer {
    static last = null;
    static failure = null;

    constructor(userAgent, options) {
        this.userAgent = userAgent;
        this.options = options;
        this.listeners = [];
        this.registered = false;
        this.unregistered = false;
        this.stateChange = {addListener: (cb) => this.listeners.push(cb)};
        FakeRegisterer.last = this;
    }

    async register() {
        if (FakeRegisterer.failure) {
            throw FakeRegisterer.failure;
        }
        this.registered = true;
        this.emit("Registered");
    }

    async unregister() {
        this.unregistered = true;
        this.emit("Unregistered");
    }

    emit(newState) {
        for (const listener of this.listeners) {
            listener({newState});
        }
    }
}

/** Double de l'Inviter / Session de SIP.js. */
class FakeInviter {
    static last = null;
    static failInvite = null;
    static dtmfCalls = [];

    constructor(userAgent, uri, options) {
        this.userAgent = userAgent;
        this.uri = uri;
        this.options = options;
        this.listeners = [];
        this.stateChange = {addListener: (cb) => this.listeners.push(cb)};
        this.accepts = 0;
        this.byes = 0;
        FakeInviter.last = this;
    }

    async invite() {
        if (FakeInviter.failInvite) {
            throw new Error(FakeInviter.failInvite);
        }
    }

    async accept() {
        this.accepts += 1;
    }

    async bye() {
        this.byes += 1;
    }

    async hold() {
        this.holds = (this.holds || 0) + 1;
    }

    async unhold() {
        this.unholds = (this.unholds || 0) + 1;
    }

    async sendDtmf(tones) {
        FakeInviter.dtmfCalls.push(tones);
    }

    async refer(uri) {
        this.referred = uri;
    }

    emit(newState) {
        for (const listener of this.listeners) {
            listener({newState});
        }
    }
}

const FAKE_SIP = {
    UserAgent: FakeUserAgent,
    Registerer: FakeRegisterer,
    Inviter: FakeInviter,
    SessionState: {Established: "Established", Terminated: "Terminated"},
    RegistererState: {Registered: "Registered", Unregistered: "Unregistered"},
    version: "0.21.2",
};

/** Remet les doubles à zéro (ils portent un état statique). */
function resetFakes() {
    FakeUserAgent.instances = [];
    FakeUserAgent.uris = [];
    FakeUserAgent.failStart = null;
    FakeRegisterer.last = null;
    FakeRegisterer.failure = null;
    FakeInviter.last = null;
    FakeInviter.failInvite = null;
    FakeInviter.dtmfCalls = [];
}

async function makeEngine({sip = FAKE_SIP, reconnectDelayMs = 0, start = true} = {}) {
    resetFakes();
    const events = [];
    const engine = new SipJsEngine({
        config: CONFIG,
        sip,
        reconnectDelayMs,
        onEvent: (type, payload) => events.push([type, payload]),
    });
    if (start) {
        await engine.start();
    }
    return {engine, events, userAgent: FakeUserAgent.instances[0]};
}

// ─── Démarrage et enregistrement ─────────────────────────────────────────────

test("le UserAgent reçoit l'AOR en identité et l'extension en authentification", async () => {
    const {userAgent} = await makeEngine();
    const options = userAgent.options;
    // From/AOR = nom d'endpoint ; l'auth SIP = l'extension (P3.2).
    assert.deepEqual(options.uri, {value: "sip:m0kxsfvz@asterisk"});
    assert.equal(options.authorizationUsername, "1011");
    assert.equal(options.authorizationPassword, "secret-1011");
    assert.equal(
        options.transportOptions.server,
        "wss://wazo-test.636.vezina.biz/api/asterisk/ws"
    );
    assert.equal(options.transportOptions.keepAliveInterval, 20);
    assert.equal(userAgent.started, true);
});

test("l'enregistrement est signalé une fois le Registerer accepté", async () => {
    const {events} = await makeEngine();
    assert.equal(FakeRegisterer.last.options.expires, 600);
    assert.deepEqual(
        events.map(([type]) => type),
        ["registered"]
    );
});

test("un client SIP.js absent est signalé sans lever", async () => {
    // ``null`` et non ``undefined`` : ``undefined`` déclencherait la valeur
    // par défaut du paramètre (et le faux SIP serait utilisé).
    const {engine, events} = await makeEngine({sip: null, start: false});
    assert.equal(await engine.start(), false);
    assert.deepEqual(events, [["error", {message: "Client SIP.js indisponible."}]]);
});

test("un transport refusé devient une erreur explicite", async () => {
    resetFakes();
    FakeUserAgent.failStart = "WSS refusé";
    const events = [];
    const engine = new SipJsEngine({
        config: CONFIG,
        sip: FAKE_SIP,
        reconnectDelayMs: 0,
        onEvent: (type, payload) => events.push([type, payload]),
    });
    assert.equal(await engine.start(), false);
    assert.deepEqual(events, [["error", {message: "WSS refusé"}]]);
    assert.equal(engine.userAgent, null);
});

test("un 401 à l'enregistrement est distingué d'un échec générique", async () => {
    resetFakes();
    FakeRegisterer.failure = {message: {statusCode: 401}};
    const events = [];
    const engine = new SipJsEngine({
        config: CONFIG,
        sip: FAKE_SIP,
        reconnectDelayMs: 0,
        onEvent: (type, payload) => events.push([type, payload]),
    });
    assert.equal(await engine.start(), false);
    assert.deepEqual(events, [["registration_failed", {statusCode: 401}]]);
});

test("le désenregistrement du Registerer est relayé", async () => {
    const {events} = await makeEngine();
    FakeRegisterer.last.emit("Unregistered");
    assert.deepEqual(
        events.map(([type]) => type),
        ["registered", "unregistered"]
    );
});

// ─── Appels ──────────────────────────────────────────────────────────────────

test("un appel entrant est relayé avec l'identité de l'appelant", async () => {
    const {engine, events, userAgent} = await makeEngine();
    const session = {
        id: "sess-in",
        remoteIdentity: {uri: {user: "2000"}, displayName: "Léa"},
        stateChange: {addListener: () => undefined},
        accept: async () => undefined,
        bye: async () => undefined,
    };
    userAgent.options.delegate.onInvite(session);
    assert.deepEqual(events.at(-1), ["incoming", {from: "2000", name: "Léa"}]);
    assert.equal(engine.hasSession, true);
});

test("un appel sortant vise sip:<cible>@<domaine> et suit l'état de session", async () => {
    const {engine, events} = await makeEngine();
    assert.equal(await engine.call("2000"), true);
    assert.deepEqual(FakeInviter.last.uri, {value: "sip:2000@asterisk"});
    FakeInviter.last.emit("Established");
    assert.deepEqual(events.at(-1), ["in_call", undefined]);
    FakeInviter.last.emit("Terminated");
    assert.deepEqual(events.at(-1), ["ended", undefined]);
    assert.equal(engine.hasSession, false, "la session est libérée");
});

test("un échec d'appel sortant est signalé", async () => {
    resetFakes();
    FakeInviter.failInvite = "486 Busy Here";
    const events = [];
    const engine = new SipJsEngine({
        config: CONFIG,
        sip: FAKE_SIP,
        reconnectDelayMs: 0,
        onEvent: (type, payload) => events.push([type, payload]),
    });
    await engine.start();
    events.length = 0;
    assert.equal(await engine.call("2000"), false);
    assert.deepEqual(events, [["error", {message: "486 Busy Here"}]]);
});

test("répondre accepte la session entrante", async () => {
    const {engine, events, userAgent} = await makeEngine();
    const session = {
        remoteIdentity: {uri: {user: "2000"}},
        stateChange: {addListener: () => undefined},
        accept: async () => undefined,
    };
    userAgent.options.delegate.onInvite(session);
    assert.equal(await engine.answer(), true);
    assert.deepEqual(events.at(-1), ["in_call", undefined]);
});

test("raccrocher termine la session puis la libère", async () => {
    const {engine} = await makeEngine();
    await engine.call("2000");
    assert.equal(await engine.hangup(), true);
    assert.equal(FakeInviter.last.byes, 1);
    assert.equal(engine.hasSession, false);
});

// ─── Cœur d'appel ────────────────────────────────────────────────────────────

test("hold et unhold visent la session courante", async () => {
    const {engine} = await makeEngine();
    await engine.call("2000");
    await engine.hold();
    await engine.unhold();
    assert.equal(FakeInviter.last.holds, 1);
    assert.equal(FakeInviter.last.unholds, 1);
});

test("le DTMF part en une seule fois (SIP.js accepte la séquence)", async () => {
    // Différence assumée avec le moteur SDK, qui exige une touche par appel.
    const {engine} = await makeEngine();
    await engine.call("2000");
    assert.equal(await engine.sendDtmf("1234*"), true);
    assert.deepEqual(FakeInviter.dtmfCalls, ["1234*"]);
});

test("le transfert envoie un REFER vers la cible", async () => {
    const {engine} = await makeEngine();
    await engine.call("2000");
    assert.equal(await engine.transfer("3000"), true);
    assert.deepEqual(FakeInviter.last.referred, {value: "sip:3000@asterisk"});
});

test("les commandes sans session ne font rien et ne lèvent pas", async () => {
    const {engine} = await makeEngine();
    assert.equal(await engine.answer(), false);
    assert.equal(await engine.hangup(), false);
    assert.equal(await engine.hold(), false);
    assert.equal(await engine.unhold(), false);
    assert.equal(await engine.sendDtmf("1"), false);
    assert.equal(await engine.transfer("3000"), false);
});

test("appeler sans UserAgent démarré ne fait rien", async () => {
    const {engine, events} = await makeEngine({start: false});
    assert.equal(await engine.call("2000"), false);
    assert.deepEqual(events, []);
});

// ─── Transport ───────────────────────────────────────────────────────────────

test("une perte de transport est signalée et déclenche la reconnexion", async () => {
    const {events, userAgent} = await makeEngine({reconnectDelayMs: 10});
    userAgent.options.delegate.onDisconnect(new Error("coupure"));
    assert.deepEqual(
        events.map(([type]) => type),
        ["registered", "transport_lost"]
    );
    await new Promise((resolve) => setTimeout(resolve, 40));
    assert.equal(userAgent.reconnects, 1);
});

test("l'arrêt désenregistre et ne relance pas la reconnexion", async () => {
    const {engine, userAgent} = await makeEngine({reconnectDelayMs: 10});
    await engine.stop();
    assert.equal(FakeRegisterer.last.unregistered, true);
    assert.equal(userAgent.stopped, true);
    userAgent.options.delegate.onDisconnect(new Error("coupure après arrêt"));
    await new Promise((resolve) => setTimeout(resolve, 40));
    assert.equal(userAgent.reconnects, 0, "on ne se reconnecte pas après l'arrêt");
});
