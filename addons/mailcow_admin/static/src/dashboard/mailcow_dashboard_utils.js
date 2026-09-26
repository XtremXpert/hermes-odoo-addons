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

/* --- Presentation partagee par les deux tableaux de bord ------------------

   Ces fonctions etaient recopiees dans chaque composant ; une copie finit
   toujours par diverger. Elles vivent ici, sans dependance, et se testent avec
   `node --test` comme le tri et le filtre. */

const ABSENT = (valeur) => valeur === null || valeur === undefined;

/** Seuils de la jauge : les memes que les alertes du serveur (80 %). */
export const SEUIL_ATTENTION = 60;
export const SEUIL_DANGER = 80;

/** La classe d'une barre de progression selon le taux, gris si inconnu. */
export function classeOccupation(pourcentage) {
    if (ABSENT(pourcentage)) {
        return "progress-bar bg-secondary";
    }
    if (pourcentage >= SEUIL_DANGER) {
        return "progress-bar bg-danger";
    }
    return pourcentage >= SEUIL_ATTENTION ? "progress-bar bg-warning" : "progress-bar bg-success";
}

/** La pastille d'une alerte selon sa gravite. */
export function classeGravite(gravite) {
    if (gravite === "danger") {
        return "text-bg-danger";
    }
    return gravite === "attention" ? "text-bg-warning" : "text-bg-secondary";
}

const RANG_GRAVITE = { danger: 0, attention: 1, information: 2 };

/** Les alertes a montrer : non vides, les plus graves d'abord.

    Le tri est stable : a gravite egale, l'ordre choisi par le serveur tient. */
export function ordonnerAlertes(alertes) {
    return (alertes || [])
        .filter((alerte) => alerte.nombre > 0)
        .map((alerte, rang) => ({ alerte, rang }))
        .sort(
            (a, b) =>
                (RANG_GRAVITE[a.alerte.gravite] ?? 3) - (RANG_GRAVITE[b.alerte.gravite] ?? 3) ||
                a.rang - b.rang
        )
        .map(({ alerte }) => alerte);
}

/** Un nombre a la francaise : « 1 234,5 ». Rien s'il manque. */
export function formaterNombre(valeur, decimales = 0) {
    if (ABSENT(valeur) || Number.isNaN(Number(valeur))) {
        return "—";
    }
    return Number(valeur).toLocaleString("fr-CA", {
        minimumFractionDigits: 0,
        maximumFractionDigits: decimales,
    });
}

/** Une taille donnee en Mo, dans l'unite qui se lit : « 59,3 Mo », « 10 Go ».

    Mailcow compte en Mo de 1024 Ko ; on garde la meme base pour que le chiffre
    concorde avec son interface. */
export function formaterTaille(mo) {
    if (ABSENT(mo) || Number.isNaN(Number(mo))) {
        return "—";
    }
    const valeur = Number(mo);
    if (Math.abs(valeur) >= 1024) {
        return `${formaterNombre(valeur / 1024, 1)} Go`;
    }
    return `${formaterNombre(valeur, 1)} Mo`;
}

/** « 12,5 % » ou « sans quota » : un taux absent n'est pas un zero. */
export function texteTaux(pourcentage) {
    return ABSENT(pourcentage) ? "sans quota" : `${formaterNombre(pourcentage, 1)} %`;
}

/** La largeur d'une barre, bornee : un depassement ne doit pas deborder. */
export function largeurBarre(pourcentage) {
    if (ABSENT(pourcentage)) {
        return "width: 0%";
    }
    return `width: ${Math.max(0, Math.min(100, pourcentage))}%`;
}
