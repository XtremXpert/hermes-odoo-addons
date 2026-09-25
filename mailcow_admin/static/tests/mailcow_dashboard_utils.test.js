/**
 * Tests de la logique de tri et de filtre du tableau de bord.
 *
 * Cette logique vit dans un module sans dependance — ni Odoo, ni OWL — pour une
 * raison precise : c'est la seule partie du tableau de bord qu'on puisse tester
 * sans navigateur. Le composant, lui, ne fait que l'appeler.
 *
 * Execution : `node --test mailcow_admin/static/tests/*.test.js`
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { basculerTri, filtrer, trier } from "../src/dashboard/mailcow_dashboard_utils.js";

const LIGNES = [
    { id: 1, nom: "zebre@exemple.com", boites_utilisees: 9 },
    { id: 2, nom: "abeille@exemple.com", boites_utilisees: 10 },
    { id: 3, nom: "castor@exemple.com", boites_utilisees: 2 },
];

test("trier range les lignes sans modifier la liste d'origine", () => {
    const resultat = trier(LIGNES, "nom", "asc");
    assert.deepEqual(resultat.map((l) => l.nom), [
        "abeille@exemple.com",
        "castor@exemple.com",
        "zebre@exemple.com",
    ]);
    assert.equal(LIGNES[0].nom, "zebre@exemple.com", "l'original ne doit pas bouger");
});

test("trier a l'envers inverse l'ordre", () => {
    assert.deepEqual(trier(LIGNES, "nom", "desc").map((l) => l.id), [1, 3, 2]);
});

test("trier compare des nombres, pas du texte", () => {
    // « 10 » < « 9 » en comparaison de chaines : le piege classique.
    assert.deepEqual(trier(LIGNES, "boites_utilisees", "asc").map((l) => l.id), [3, 1, 2]);
    assert.deepEqual(trier(LIGNES, "boites_utilisees", "desc").map((l) => l.id), [2, 1, 3]);
});

test("trier sans cle connue rend la liste telle quelle", () => {
    assert.deepEqual(trier(LIGNES, null, "asc").map((l) => l.id), [1, 2, 3]);
});

test("filtrer cherche dans les champs demandes, sans tenir compte de la casse", () => {
    const trouvees = filtrer(LIGNES, "CASTOR", ["nom"]);
    assert.deepEqual(trouvees.map((l) => l.id), [3]);
});

test("filtrer un texte vide rend tout, et un texte absent rend rien", () => {
    assert.equal(filtrer(LIGNES, "", ["nom"]).length, 3);
    assert.equal(filtrer(LIGNES, "   ", ["nom"]).length, 3);
    assert.equal(filtrer(LIGNES, "introuvable", ["nom"]).length, 0);
});

test("filtrer accepte plusieurs champs, dont des nombres", () => {
    const trouvees = filtrer(LIGNES, "10", ["nom", "boites_utilisees"]);
    assert.deepEqual(trouvees.map((l) => l.id), [2]);
});

test("basculerTri monte, puis descend, puis oublie", () => {
    let tri = null;
    tri = basculerTri(tri, "nom");
    assert.deepEqual(tri, { cle: "nom", sens: "asc" });
    tri = basculerTri(tri, "nom");
    assert.deepEqual(tri, { cle: "nom", sens: "desc" });
    tri = basculerTri(tri, "nom");
    assert.equal(tri, null, "un troisieme clic doit revenir a l'ordre naturel");
});

test("basculerTri repart a zero quand on change de colonne", () => {
    const tri = basculerTri({ cle: "nom", sens: "desc" }, "boites_utilisees");
    assert.deepEqual(tri, { cle: "boites_utilisees", sens: "asc" });
});
