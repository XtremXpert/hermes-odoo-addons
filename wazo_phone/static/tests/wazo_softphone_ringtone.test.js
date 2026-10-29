import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import {runInNewContext} from "node:vm";

// Run the actual audio methods without bootstrapping the Odoo web client.
const source = readFileSync(new URL(
    "../src/softphone/wazo_softphone_service.esm.js", import.meta.url
), "utf8");
const methods = source.slice(
    source.indexOf("    _startRingtone() {"),
    source.indexOf("    _setState(state, message) {")
);

function setup() {
    const audios = [];
    const contexts = [];
    const timers = new Map();
    let nextTimer = 0;
    class Audio {
        constructor() {
            audios.push(this);
            this.paused = false;
        }
        play() {
            return new Promise((resolve, reject) => {
                this.resolve = resolve;
                this.reject = reject;
            });
        }
        pause() {
            this.paused = true;
            this.reject(new Error("play interrupted"));
        }
        load() {}
    }
    class AudioContext {
        constructor() {
            contexts.push(this);
            this.state = "running";
            this.currentTime = 0;
            this.nodes = [];
        }
        createOscillator() {
            const node = {
                frequency: {}, connect() {}, start() {},
                stopped: false,
                stop() { this.stopped = true; },
            };
            this.nodes.push(node);
            return node;
        }
        createGain() {
            return {connect() {}, gain: {
                setValueAtTime() {}, linearRampToValueAtTime() {},
            }};
        }
        close() { this.state = "closed"; return Promise.resolve(); }
        resume() { return Promise.resolve(); }
    }
    const schedule = (fn) => { timers.set(++nextTimer, fn); return nextTimer; };
    const Service = runInNewContext(`(class {${methods}})`, {
        Audio, window: {AudioContext},
        setTimeout: schedule, setInterval: schedule,
        clearTimeout: (id) => timers.delete(id),
        clearInterval: (id) => timers.delete(id),
    });
    return {service: new Service(), audios, contexts, timers};
}

const flush = async () => { await Promise.resolve(); };

test("repeated incoming notifications play only one audio", () => {
    const {service, audios} = setup();
    service._startRingtone();
    service._startRingtone();
    assert.equal(audios.length, 1);
});

test("answering during pending play never restarts the ringtone", async () => {
    const {service, audios, contexts, timers} = setup();
    service._startRingtone();
    service._stopRingtone();
    await flush();
    assert.equal(audios[0].paused, true);
    assert.equal(contexts.length, 0);
    assert.equal(timers.size, 0);
});

test("a late rejection from an old call cannot replace the new ringtone", async () => {
    const {service, audios, contexts} = setup();
    service._startRingtone();
    service._stopRingtone();
    service._startRingtone();
    await flush();
    assert.equal(service._ringAudio, audios[1]);
    assert.equal(contexts.length, 0);
});

test("fallback and normal audio never overlap on repeated notifications", async () => {
    const {service, audios, contexts, timers} = setup();
    service._startRingtone();
    audios[0].reject(new Error("audio unavailable"));
    await flush();
    service._startRingtone();
    assert.equal(audios.length, 1);
    assert.equal(contexts.length, 1);
    assert.equal(audios[0].paused, true);
    service._stopRingtone();
    assert.ok(contexts[0].nodes.every((node) => node.stopped));
    assert.equal(timers.size, 0);
});

test("a second call gets a usable audio context after fallback was stopped", async () => {
    const {service, audios, contexts} = setup();
    for (let i = 0; i < 2; i++) {
        service._startRingtone();
        audios[i].reject(new Error("audio unavailable"));
        await flush();
        assert.equal(contexts[i].state, "running");
        service._stopRingtone();
        assert.equal(contexts[i].state, "closed");
        assert.equal(service._audioCtx, null);
    }
});

test("the safety timeout stops fallback audio as well", async () => {
    const {service, audios, contexts, timers} = setup();
    service._startRingtone();
    const timeout = timers.get(service._ringTimeout);
    audios[0].reject(new Error("audio unavailable"));
    await flush();
    timeout();
    assert.equal(contexts[0].state, "closed");
    assert.equal(timers.size, 0);
});
