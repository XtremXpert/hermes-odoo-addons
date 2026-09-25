/** @odoo-module **/
/* Tri, filtre et etat de tri du tableau de bord Mailcow.

   Ce module n'importe rien : ni Odoo, ni OWL. C'est delibere. C'est la seule
   partie du tableau de bord qu'on puisse eprouver sans navigateur, avec
   `node --test`, donc la seule qui soit reellement verifiee a chaque
   integration continue. Le composant l'appelle ; il ne reimplemente rien. */

/** Compare deux valeurs : les nombres en nombres, le reste en texte.

    `numeric: true` fait que « 10 » se range apres « 9 ». Sans lui, l'ordre
    alphabetique placerait 10 avant 9 — le piege classique du tri de colonnes. */
function comparer(gauche, droite) {
    const vide = (valeur) => valeur === null || valeur === undefined;
    if (vide(gauche) && vide(droite)) {
        return 0;
    }
    if (vide(gauche)) {
        return -1;
    }
    if (vide(droite)) {
        return 1;
    }
    if (typeof gauche === "number" && typeof droite === "number") {
        return gauche - droite;
    }
    return String(gauche).localeCompare(String(droite), "fr", { numeric: true });
}

/** La liste triee, sans toucher a celle qu'on donne. */
export function trier(lignes, cle, sens) {
    if (!cle) {
        return [...lignes];
    }
    const facteur = sens === "desc" ? -1 : 1;
    return [...lignes].sort((a, b) => facteur * comparer(a[cle], b[cle]));
}

/** Les lignes dont un des champs contient le texte cherche, sans egard a la casse. */
export function filtrer(lignes, texte, cles) {
    const cherche = String(texte || "").trim().toLowerCase();
    if (!cherche) {
        return [...lignes];
    }
    return lignes.filter((ligne) =>
        cles.some((cle) => {
            const valeur = ligne[cle];
            return (
                valeur !== null &&
                valeur !== undefined &&
                String(valeur).toLowerCase().includes(cherche)
            );
        })
    );
}

/** L'etat de tri suivant : croissant, decroissant, puis aucun.

    Un troisieme clic revient a l'ordre naturel : sans cela, on ne peut jamais
    retrouver la liste telle que le serveur l'a pensee. */
export function basculerTri(tri, cle) {
    if (!tri || tri.cle !== cle) {
        return { cle, sens: "asc" };
    }
    if (tri.sens === "asc") {
        return { cle, sens: "desc" };
    }
    return null;
}
