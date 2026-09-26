/**
 * Tests de l'arbitrage multi-onglets du softphone (P3.3e).
 *
 * Le problème résolu ici est **côté navigateur** : avec N onglets Odoo
 * ouverts, chaque onglet croit être le téléphone (N enregistrements SIP,
 * sonnerie multiple, double décroché, états divergents). L'arbitrage élit
 * UN onglet propriétaire de la couche SIP et fait des autres des
 * télécommandes du même appel.
 *
 * Exécution : `node --test wazo_phone/static/tests/`
 *
 * Les adaptateurs (verrou exclusif, canal de diffusion) sont injectés :
 * les tests câblent deux arbitres sur un verrou et un canal partagés, ce
 * qui reproduit fidèlement deux onglets du même navigateur.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { SoftphoneArbiter } from "../src/softphone/wazo_softphone_arbiter.js";

// ─── Adaptateurs de test (doubles du navigateur) ─────────────────────────────

/**
 * Verrou exclusif partagé (équivalent de ``navigator.locks``).
 *
 * Une seule détention à la fois : les demandes concurrentes sont mises en
 * file et servies dans l'ordre, comme le fait l'implémentation du
 * navigateur pour un verrou ``mode: "exclusive"``.
 */
class FakeLockManager {
    constructor() {
        this.holder = null;
        this.queue = [];
    }

    request(name, options, callback) {
        return new Promise((resolve) => {
            const entry = { name, callback, resolve };
            if (this.holder === null) {
                this.holder = entry;
                this._run(entry);
            } else {
                this.queue.push(entry);
            }
        });
    }

    _run(entry) {
        Promise.resolve(entry.callback()).then(() => {
            this._release(entry);
        });
    }

    _release(entry) {
        if (this.holder !== entry) {
            return;
        }
        this.holder = null;
        entry.resolve();
        const next = this.queue.shift();
        if (next) {
            this.holder = next;
            this._run(next);
        }
    }
}

/**
 * Canal de diffusion partagé (équivalent de ``BroadcastChannel``).
 *
 * Le message est délivré aux AUTRES ports du même nom, jamais à
 * l'émetteur — c'est la sémantique réelle de ``BroadcastChannel``.
 */
class FakeChannelHub {
    constructor() {
        this.ports = new Set();
    }

    connect() {
        const hub = this;
        const port = {
            onmessage: null,
            closed: false,
            postMessage(data) {
                // ``BroadcastChannel`` ne livre pas dans la foulée : le
                // message est mis en file et remis à la boucle d'événements
                // du port destinataire. C'est cette asynchronie qui rend la
                // course « deux onglets décrochent en même temps » réelle —
                // un double synchrone masquerait le cas.
                const message = { data: JSON.parse(JSON.stringify(data)) };
                for (const other of hub.ports) {
                    if (other !== port && !other.closed) {
                        queueMicrotask(() => {
                            if (!other.closed && other.onmessage) {
                                other.onmessage(message);
                            }
                        });
                    }
                }
            },
            close() {
                port.closed = true;
                hub.ports.delete(port);
            },
        };
        hub.ports.add(port);
        return port;
    }
}

/** Câble N arbitres sur un verrou et un canal partagés. */
function makeTabs(count, { locks = new FakeLockManager(), hub = new FakeChannelHub() } = {}) {
    const tabs = [];
    for (let i = 0; i < count; i++) {
        tabs.push(
            new SoftphoneArbiter({
                tabId: `tab-${i}`,
                locks,
                createChannel: () => hub.connect(),
            })
        );
    }
    return { tabs, locks, hub };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

// ─── Élection du propriétaire de la couche SIP ───────────────────────────────

test("un seul onglet devient propriétaire, les autres non", async () => {
    const { tabs } = makeTabs(3);
    for (const tab of tabs) {
        tab.start();
    }
    await flush();

    const leaders = tabs.filter((tab) => tab.isLeader);
    assert.equal(leaders.length, 1, "un seul onglet doit détenir la couche SIP");
    assert.equal(leaders[0], tabs[0], "le premier demandeur obtient le verrou");
    // Seul le propriétaire enregistre : c'est tout l'objet de l'arbitrage.
    assert.deepEqual(
        tabs.map((tab) => tab.shouldRegister),
        [true, false, false]
    );
});

test("le verrou tenu par un onglet n'est pas pris par un arrivant", async () => {
    const { tabs, locks, hub } = makeTabs(1);
    tabs[0].start();
    await flush();
    assert.equal(tabs[0].isLeader, true);

    // Un second onglet arrive plus tard (cas réel : ouverture d'un nouvel
    // onglet pendant un appel).
    const newcomer = new SoftphoneArbiter({
        tabId: "tab-late",
        locks,
        createChannel: () => hub.connect(),
    });
    newcomer.start();
    await flush();
    assert.equal(newcomer.isLeader, false, "le verrou est déjà détenu");
    assert.equal(newcomer.shouldRegister, false);
});

test("le suivant reprend la main quand le propriétaire se retire", async () => {
    const { tabs } = makeTabs(2);
    tabs[0].start();
    tabs[1].start();
    await flush();
    assert.equal(tabs[0].isLeader, true);

    tabs[0].stop();
    await flush();
    assert.equal(tabs[1].isLeader, true, "le verrou passe au suivant");
    assert.equal(tabs[1].shouldRegister, true);
});

test("un appel en cours survit au retrait du propriétaire", async () => {
    // Le verrou ne porte que la couche SIP/navigateur : l'appel vit côté
    // Wazo (session SIP), pas dans l'onglet. Le successeur doit donc se
    // ré-enregistrer sans conclure à une fin d'appel.
    const { tabs } = makeTabs(2);
    tabs[0].start();
    tabs[1].start();
    await flush();
    tabs[0].broadcastIncoming({ from: "2000", name: "Léa" });
    await flush();
    assert.equal(tabs[1].incoming.from, "2000");

    tabs[0].stop();
    await flush();
    assert.equal(tabs[1].isLeader, true);
    assert.ok(
        tabs[1].incoming,
        "le successeur conserve l'appel entrant en cours"
    );
});

test("sans verrou disponible, l'onglet reste utilisable seul", async () => {
    // Repli : navigateur sans Web Locks (ou contexte non sécurisé). On ne
    // doit PAS casser le softphone — un seul onglet se comporte comme avant.
    const arbiter = new SoftphoneArbiter({
        tabId: "tab-solo",
        locks: null,
        createChannel: null,
    });
    await arbiter.start();
    assert.equal(arbiter.isLeader, true, "repli mono-onglet");
    assert.equal(arbiter.shouldRegister, true);
    arbiter.stop();
});

// ─── Appel entrant : tous les onglets sonnent ────────────────────────────────

test("l'appel entrant est diffusé à tous les onglets", async () => {
    const { tabs } = makeTabs(3);
    for (const tab of tabs) {
        tab.start();
    }
    await flush();

    tabs[0].broadcastIncoming({ from: "2000", name: "Léa" });
    await flush();
    for (const tab of tabs) {
        assert.equal(tab.incoming?.from, "2000",
            "chaque onglet doit sonner, pas seulement le propriétaire");
    }
});

// ─── Revendication de l'appel (claimed) ──────────────────────────────────────

test("la première revendication gagne, l'autre onglet devient télécommande", async () => {
    const { tabs } = makeTabs(2);
    for (const tab of tabs) {
        tab.start();
    }
    await flush();
    tabs[0].broadcastIncoming({ from: "2000" });
    await flush();

    assert.equal(tabs[1].claim(), true, "l'onglet non propriétaire peut répondre");
    await flush();
    assert.equal(tabs[1].isOwner, true);
    assert.equal(tabs[0].isOwner, false,
        "le propriétaire n'est pas le maître de l'appel pour autant");
});

test("un onglet ne peut pas voler une revendication déjà posée", async () => {
    const { tabs } = makeTabs(2);
    for (const tab of tabs) {
        tab.start();
    }
    await flush();
    tabs[1].broadcastIncoming({ from: "2000" });
    await flush();

    tabs[1].claim();
    await flush();
    assert.equal(tabs[1].isOwner, true);
    assert.equal(tabs[0].claim(), false,
        "une revendication posée est refusée aux autres");
    await flush();
    assert.equal(tabs[0].isOwner, false);
});

test("deux revendications simultanées se départagent de façon déterministe", async () => {
    // Course réelle : deux onglets cliquent « répondre » au même instant.
    // Le départage doit être identique dans les deux onglets (sinon l'appel
    // est répondu deux fois) — on tranche par identifiant d'onglet.
    const { tabs } = makeTabs(2);
    for (const tab of tabs) {
        tab.start();
    }
    await flush();
    tabs[0].broadcastIncoming({ from: "2000" });
    await flush();

    const results = [tabs[0].claim(), tabs[1].claim()];
    await flush();
    assert.deepEqual(results, [true, true], "les deux tentent leur chance");
    assert.equal(tabs[0].isOwner, true, "tab-0 (identifiant inférieur) l'emporte");
    assert.equal(tabs[1].isOwner, false);
    assert.equal(tabs[0].claimedBy, tabs[1].claimedBy,
        "les deux onglets doivent s'accorder sur le propriétaire");
    assert.equal(tabs[0].claimedBy, "tab-0");
});

test("la fin d'appel libère la revendication partout", async () => {
    const { tabs } = makeTabs(2);
    for (const tab of tabs) {
        tab.start();
    }
    await flush();
    tabs[0].broadcastIncoming({ from: "2000" });
    await flush();
    tabs[1].claim();
    await flush();
    assert.equal(tabs[1].isOwner, true);

    tabs[1].release();
    await flush();
    assert.equal(tabs[1].claimedBy, null);
    assert.equal(tabs[0].claimedBy, null, "libéré aussi dans l'autre onglet");
    assert.equal(tabs[1].incoming, null, "l'appel entrant est clôturé");
});

// ─── Télécommande : les commandes remontent au propriétaire SIP ──────────────

test("seul le propriétaire exécute ; les autres télécommandent", async () => {
    const { tabs } = makeTabs(2);
    for (const tab of tabs) {
        tab.start();
    }
    await flush();

    assert.equal(tabs[0].shouldForward, false, "le propriétaire exécute lui-même");
    assert.equal(tabs[1].shouldForward, true,
        "un non-propriétaire doit relayer ses commandes (hold, DTMF, transfert)");
});

test("les commandes d'un onglet télécommande atteignent le propriétaire", async () => {
    const { tabs } = makeTabs(2);
    const received = [];
    tabs[0].onCommand = (name, payload) => received.push([name, payload]);
    for (const tab of tabs) {
        tab.start();
    }
    await flush();

    tabs[1].forwardCommand("dtmf", { tones: "12" });
    await flush();
    assert.deepEqual(received, [["dtmf", { tones: "12" }]]);
});

// ─── Reprise du rôle par un autre onglet ─────────────────────────────────────

test("le successeur est prévenu qu'il devient propriétaire", async () => {
    // Sans cette notification, fermer l'onglet propriétaire rendrait le
    // téléphone muet : le successeur doit démarrer SA couche SIP.
    const { tabs } = makeTabs(2);
    const events = [[], []];
    tabs[0].onLeadership = (value) => events[0].push(value);
    tabs[1].onLeadership = (value) => events[1].push(value);
    for (const tab of tabs) {
        tab.start();
    }
    await flush();
    assert.deepEqual(events[0], [true], "le premier demandeur est prévenu");
    assert.deepEqual(events[1], [], "l'attente ne déclenche rien");

    tabs[0].stop();
    await flush();
    assert.deepEqual(events[1], [true],
        "le successeur doit pouvoir démarrer sa couche SIP");
    assert.deepEqual(events[0], [true, false], "le partant est prévenu");
});

test("un onglet non propriétaire est prévenu de l'appel entrant", async () => {
    const { tabs } = makeTabs(2);
    const rings = [];
    tabs[1].onIncoming = (info) => rings.push(info);
    for (const tab of tabs) {
        tab.start();
    }
    await flush();

    tabs[0].broadcastIncoming({ from: "2000", name: "Léa" });
    await flush();
    assert.deepEqual(rings, [{ from: "2000", name: "Léa" }],
        "l'onglet télécommande doit faire sonner l'appel");
});

// ─── Robustesse ──────────────────────────────────────────────────────────────

test("les messages illisibles ou étrangers sont ignorés sans casser l'état", async () => {
    const { tabs } = makeTabs(1);
    tabs[0].start();
    await flush();
    tabs[0].claim();
    await flush();

    for (const garbage of [
        null,
        undefined,
        42,
        "texte",
        {},
        { type: "inconnu" },
        { type: "claim" }, // sans tabId
        { type: "state", payload: { state: "in_call" }, tabId: "x" },
    ]) {
        tabs[0].handleMessage(garbage);
    }
    assert.equal(tabs[0].claimedBy, "tab-0",
        "un message invalide ne doit pas perturber la revendication");
});

test("un état diffusé par un homologue est reflété localement", async () => {
    const { tabs } = makeTabs(2);
    const seen = [];
    tabs[1].onState = (state) => seen.push(state);
    for (const tab of tabs) {
        tab.start();
    }
    await flush();

    tabs[0].publishState({ state: "in_call", peer: "2000" });
    await flush();
    assert.deepEqual(seen, [{ state: "in_call", peer: "2000" }],
        "les onglets non propriétaires suivent l'état de l'appel");
});
