/**
 * Tests de la logique de tri et de filtre du tableau de bord.
 *
 * Cette logique vit dans un module sans dependance — ni Odoo, ni OWL — pour une
 * raison precise : c'est la seule partie du tableau de bord qu'on puisse tester
 * sans navigateur. Le composant, lui, ne fait que l'appeler.
 *
 * Execution : `node --test mailcow/static/tests/*.test.js`
 */
import assert from "node:assert/strict";
import {test} from "node:test";

import {
    basculerTri,
    classeOccupation,
    filtrer,
    formaterNombre,
    formaterTaille,
    largeurBarre,
    ordonnerAlertes,
    texteTaux,
    trier,
} from "../src/dashboard/mailcow_dashboard_utils.esm.js";

const LIGNES = [
    {id: 1, nom: "zebre@exemple.com", boites_utilisees: 9},
    {id: 2, nom: "abeille@exemple.com", boites_utilisees: 10},
    {id: 3, nom: "castor@exemple.com", boites_utilisees: 2},
];

test("trier range les lignes sans modifier la liste d'origine", () => {
    const resultat = trier(LIGNES, "nom", "asc");
    assert.deepEqual(
        resultat.map((l) => l.nom),
        ["abeille@exemple.com", "castor@exemple.com", "zebre@exemple.com"]
    );
    assert.equal(LIGNES[0].nom, "zebre@exemple.com", "l'original ne doit pas bouger");
});

test("trier a l'envers inverse l'ordre", () => {
    assert.deepEqual(
        trier(LIGNES, "nom", "desc").map((l) => l.id),
        [1, 3, 2]
    );
});

test("trier compare des nombres, pas du texte", () => {
    // « 10 » < « 9 » en comparaison de chaines : le piege classique.
    assert.deepEqual(
        trier(LIGNES, "boites_utilisees", "asc").map((l) => l.id),
        [3, 1, 2]
    );
    assert.deepEqual(
        trier(LIGNES, "boites_utilisees", "desc").map((l) => l.id),
        [2, 1, 3]
    );
});

test("trier sans cle connue rend la liste telle quelle", () => {
    assert.deepEqual(
        trier(LIGNES, null, "asc").map((l) => l.id),
        [1, 2, 3]
    );
});

test("filtrer cherche dans les champs demandes, sans tenir compte de la casse", () => {
    const trouvees = filtrer(LIGNES, "CASTOR", ["nom"]);
    assert.deepEqual(
        trouvees.map((l) => l.id),
        [3]
    );
});

test("filtrer un texte vide rend tout, et un texte absent rend rien", () => {
    assert.equal(filtrer(LIGNES, "", ["nom"]).length, 3);
    assert.equal(filtrer(LIGNES, "   ", ["nom"]).length, 3);
    assert.equal(filtrer(LIGNES, "introuvable", ["nom"]).length, 0);
});

test("filtrer accepte plusieurs champs, dont des nombres", () => {
    const trouvees = filtrer(LIGNES, "10", ["nom", "boites_utilisees"]);
    assert.deepEqual(
        trouvees.map((l) => l.id),
        [2]
    );
});

test("basculerTri monte, puis descend, puis oublie", () => {
    let tri = null;
    tri = basculerTri(tri, "nom");
    assert.deepEqual(tri, {cle: "nom", sens: "asc"});
    tri = basculerTri(tri, "nom");
    assert.deepEqual(tri, {cle: "nom", sens: "desc"});
    tri = basculerTri(tri, "nom");
    assert.equal(tri, null, "un troisieme clic doit revenir a l'ordre naturel");
});

test("basculerTri repart a zero quand on change de colonne", () => {
    const tri = basculerTri({cle: "nom", sens: "desc"}, "boites_utilisees");
    assert.deepEqual(tri, {cle: "boites_utilisees", sens: "asc"});
});

// Les separateurs de « fr-CA » sont des espaces insecables : on les ramene a
// des espaces ordinaires pour que les attentes restent lisibles.
const lisible = (texte) => texte.replace(/[\u00a0\u202f]/g, " ");

test("formaterTaille choisit l'unite qui se lit", () => {
    assert.equal(lisible(formaterTaille(59.3)), "59,3 Mo");
    assert.equal(lisible(formaterTaille(0)), "0 Mo");
    assert.equal(lisible(formaterTaille(10240)), "10 Go");
    assert.equal(lisible(formaterTaille(3072)), "3 Go");
    assert.equal(lisible(formaterTaille(1536)), "1,5 Go");
});

test("formaterTaille et formaterNombre ne fabriquent pas de zero", () => {
    assert.equal(formaterTaille(null), "\u2014");
    assert.equal(formaterTaille(undefined), "\u2014");
    assert.equal(formaterNombre(null), "\u2014");
});

test("formaterNombre separe les milliers", () => {
    assert.equal(lisible(formaterNombre(1234567)), "1 234 567");
    assert.equal(lisible(formaterNombre(12.345, 1)), "12,3");
});

test("texteTaux distingue « sans quota » de « vide »", () => {
    assert.equal(texteTaux(null), "sans quota");
    assert.equal(lisible(texteTaux(0)), "0 %");
    assert.equal(lisible(texteTaux(12.5)), "12,5 %");
});

test("classeOccupation suit les seuils des alertes", () => {
    assert.equal(classeOccupation(null), "progress-bar bg-secondary");
    assert.equal(classeOccupation(59.9), "progress-bar bg-success");
    assert.equal(classeOccupation(60), "progress-bar bg-warning");
    assert.equal(classeOccupation(80), "progress-bar bg-danger");
});

test("largeurBarre ne deborde jamais", () => {
    assert.equal(largeurBarre(150), "width: 100%");
    assert.equal(largeurBarre(-3), "width: 0%");
    assert.equal(largeurBarre(null), "width: 0%");
    assert.equal(largeurBarre(42.5), "width: 42.5%");
});

test("ordonnerAlertes ecarte les vides et met les plus graves d'abord", () => {
    const alertes = [
        {cle: "info", gravite: "information", nombre: 3},
        {cle: "a1", gravite: "attention", nombre: 1},
        {cle: "vide", gravite: "danger", nombre: 0},
        {cle: "d1", gravite: "danger", nombre: 2},
        {cle: "a2", gravite: "attention", nombre: 5},
    ];
    assert.deepEqual(
        ordonnerAlertes(alertes).map((a) => a.cle),
        ["d1", "a1", "a2", "info"]
    );
    assert.deepEqual(ordonnerAlertes(null), []);
});
