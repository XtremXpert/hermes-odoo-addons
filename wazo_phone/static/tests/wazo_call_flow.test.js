/** Tests Node du bouclage d'appel (``wazo_call_flow.esm.js``). */
import {describe, test} from "node:test";
import assert from "node:assert/strict";

import {
    buildCallInfo,
    finalizePayload,
    isDuplicateIncoming,
    isEmptyMissedNotice,
} from "../src/softphone/wazo_call_flow.esm.js";

describe("buildCallInfo", () => {
    test("normalise la fiche d'appel", () => {
        const call = buildCallInfo({direction: "inbound", num: "5145550100", startedAt: 1000});
        assert.deepEqual(call, {
            direction: "inbound",
            num: "5145550100",
            name: "",
            answered: false,
            startedAt: 1000,
        });
    });

    test("direction absente : repli sortant", () => {
        assert.equal(buildCallInfo({num: "1001"}).direction, "outbound");
    });
});

describe("finalizePayload", () => {
    test("sans appel suivi : rien à consigner", () => {
        assert.equal(finalizePayload(null), null);
        assert.equal(finalizePayload({}), null);
    });

    test("produit la charge utile avec la durée écoulée", () => {
        const call = buildCallInfo({direction: "inbound", num: "1011", startedAt: 1000});
        call.answered = true;
        const payload = finalizePayload(call, 90000);
        assert.equal(payload.num, "1011");
        assert.equal(payload.direction, "inbound");
        assert.equal(payload.answered, true);
        assert.equal(payload.duration, 89);
    });

    test("durée plancher à zéro", () => {
        const call = buildCallInfo({direction: "outbound", num: "2000", startedAt: 5000});
        assert.equal(finalizePayload(call, 4999).duration, 0);
    });
});

describe("isDuplicateIncoming", () => {
    const payload = {num: "5145550100"};

    test("ignorée si la session sonne déjà", () => {
        assert.equal(
            isDuplicateIncoming({state: "ringing", currentCall: null, payload}),
            true
        );
    });

    test("ignorée si un appel est en cours", () => {
        for (const state of ["in_call", "outbound"]) {
            assert.equal(
                isDuplicateIncoming({state, currentCall: null, payload}),
                true
            );
        }
    });

    test("ignorée si c'est l'appel déjà suivi", () => {
        const currentCall = buildCallInfo({direction: "inbound", num: "5145550100"});
        assert.equal(
            isDuplicateIncoming({state: "registered", currentCall, payload}),
            true
        );
    });

    test("reçue quand la session est libre", () => {
        assert.equal(
            isDuplicateIncoming({state: "registered", currentCall: null, payload}),
            false
        );
    });

    test("reçue pour un autre numéro que l'appel suivi", () => {
        const currentCall = buildCallInfo({direction: "outbound", num: "2000"});
        assert.equal(
            isDuplicateIncoming({state: "ended", currentCall, payload}),
            false
        );
    });

    test("charge vide : ignorée", () => {
        assert.equal(
            isDuplicateIncoming({state: "registered", currentCall: null, payload: null}),
            true
        );
    });
});

describe("isEmptyMissedNotice", () => {
    test("vide sans numéro ni nom", () => {
        assert.equal(isEmptyMissedNotice(null), true);
        assert.equal(isEmptyMissedNotice({}), true);
    });

    test("non vide avec un numéro", () => {
        assert.equal(isEmptyMissedNotice({num: "1011"}), false);
        assert.equal(isEmptyMissedNotice({name: "Client"}), false);
    });
});
