/**
 * Contrat de gabarit du softphone (Odoo 20, client OWL 2).
 *
 * Deux règles, apprises en direct sur le client **servi** :
 *
 * 1. **Un membre du composant se lit avec ``this.``.** Dans un gabarit, un nom
 *    nu n'est pas résolu sur le composant : il vaut ``undefined``, et le
 *    navigateur lève « Cannot read properties of undefined (reading 'state') ».
 *    Le symptôme est parfaitement muet côté serveur — journal propre, suite
 *    Python verte, tests JS verts — parce que rien d'autre ne lit nos gabarits.
 *    Même angle mort que ``this.service.foo()`` appelé sur un getter.
 * 2. **Le rendu manuel ``@web/owl2/utils.render`` (OWL 1) est proscrit.** Il est
 *    déprécié, et le service est déjà réactif (il rend ``proxy(this)``) : ce
 *    helper n'apporte rien et re-rend le composant avec un contexte hérité.
 *
 * Exécution : `node --test wazo_phone/static/tests/`
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const ICI = dirname(fileURLToPath(import.meta.url));
const SOURCE = join(ICI, "..", "src", "softphone");
const GABARIT = join(SOURCE, "wazo_softphone_templates.xml");

/** Métat du composant : lu par le gabarit, donc à préfixer par ``this.``. */
const MEMBRES = [
    "service",
    "state",
    "statusIcon",
    "statusText",
    "isUsable",
    "isRinging",
    "isInCall",
    "isOutbound",
    "isHeld",
    "caller",
    "callLog",
    "dtmfKeys",
    "target",
    "dtmfTones",
    "transferTarget",
    "activeTab",
];

/** Gestionnaires et formateurs branchés par le gabarit. */
const METHODES = [
    "onClose",
    "onCall",
    "onAnswer",
    "onHangup",
    "onHoldToggle",
    "onSendDtmf",
    "onDtmfKey",
    "onDtmfInput",
    "onTransfer",
    "onTransferInput",
    "onTargetInput",
    "onTabChange",
    "formatDuration",
    "formatDateTime",
];

/**
 * Occurrences d'un nom employé **nu**, c'est-à-dire ni après un point
 * (``service.state`` est une propriété, pas un nom à résoudre) ni collé à un
 * autre mot.
 *
 * @param {string} source
 * @param {string} nom
 * @returns {Array<{ligne: number, texte: string}>}
 */
function occurrencesNues(source, nom) {
    const motif = new RegExp(String.raw`(?<![\w.$])${nom}\b`, "g");
    const trouvailles = [];
    source.split("\n").forEach((texte, index) => {
        motif.lastIndex = 0;
        if (motif.test(texte)) {
            trouvailles.push({ ligne: index + 1, texte: texte.trim() });
        }
    });
    return trouvailles;
}

test("le gabarit du panneau ne lit pas de membre nu", () => {
    const gabarit = readFileSync(GABARIT, "utf8");
    const nus = [];
    for (const nom of [...MEMBRES, ...METHODES]) {
        for (const trouvee of occurrencesNues(gabarit, nom)) {
            nus.push(`${nom} (ligne ${trouvee.ligne}) : ${trouvee.texte}`);
        }
    }
    assert.deepEqual(
        nus,
        [],
        "Un nom nu dans un gabarit vaut undefined dans le client : " +
            "préfixez-le par « this. ».\n" +
            nus.join("\n")
    );
});

test("le gabarit de l'item systray, lui, est conforme", () => {
    // Témoin : c'est le gabarit qui fonctionne, il sert de modèle.
    const gabarit = readFileSync(GABARIT, "utf8");
    assert.match(gabarit, /this\.service\.state/);
});

/**
 * Retire commentaires de bloc et de ligne.
 *
 * Une règle de style ne doit pas s'appliquer à la prose qui l'explique : nos
 * en-têtes citent ``@web/owl2/utils.render`` précisément pour dire de ne pas
 * l'employer.
 *
 * @param {string} source
 * @returns {string}
 */
function sansCommentaires(source) {
    return source
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "");
}

test("aucune source du softphone n'emploie le rendu manuel OWL 1", () => {
    const fautifs = [];
    for (const fichier of [
        "wazo_softphone.js",
        "wazo_softphone_app.js",
        "wazo_systray_item.js",
        "wazo_softphone_service.js",
        "wazo_softphone_arbiter.js",
    ]) {
        const source = sansCommentaires(
            readFileSync(join(SOURCE, fichier), "utf8")
        );
        if (source.includes("@web/owl2/utils")) {
            fautifs.push(`${fichier} : importe @web/owl2/utils`);
        }
        if (/\brender\s*\(/.test(source)) {
            fautifs.push(`${fichier} : appelle render(...)`);
        }
    }
    assert.deepEqual(
        fautifs,
        [],
        "Le rendu manuel est déprécié et re-rend avec un contexte hérité : " +
            "comptez sur la réactivité d'OWL.\n" +
            fautifs.join("\n")
    );
});
