/** @odoo-module **/
/* Tableau de bord d'un domaine : un domaine a la fois.

   Le tableau d'ensemble repond a « ou regarder » ; celui-ci a « qu'y a-t-il
   ici ». Il ne recompte rien de son cote : le serveur lui rend un instantane
   deja mesure, et les regles d'alerte sont exactement celles de l'ensemble —
   seule la portee change. Un detail qui se calculerait lui-meme finirait par
   contredire la vue d'ensemble, et l'un des deux serait faux.

   Regles d'OWL 3, apprises sur ce module : l'etat passe par « proxy », et le
   gabarit qualifie par « this. » tout ce qui appartient au composant. Un
   gabarit ne peut appeler que ce qui existe ici : chaque appel `this.x(` du
   gabarit doit avoir son membre, sans quoi le rendu echoue.

   Le tri et le filtre viennent de mailcow_dashboard_utils.js, couverts par
   `node --test` a chaque integration continue.

   Le rafraichissement relit l'etat local d'Odoo, jamais Mailcow : ouvrir un
   domaine ne doit pas charger le serveur de courriel. */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, proxy } from "@odoo/owl";

import {
    basculerTri,
    classeGravite,
    classeOccupation,
    filtrer,
    formaterNombre,
    formaterTaille,
    largeurBarre,
    ordonnerAlertes,
    texteTaux,
    trier,
} from "./mailcow_dashboard_utils";

const INTERVALLE_MS = 30000;
const CHAMPS_RECHERCHE = {
    boites: ["nom", "quota_utilise_mb", "messages", "derniere_connexion"],
    alias: ["nom", "destinations"],
};

export class MailcowDomainDashboard extends Component {
    static template = "mailcow_admin.DashboardDomaine";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            chargement: true,
            donnees: null,
            erreur: null,
            synchro: false,
            onglet: "boites",
            recherche: "",
            tri: null,
            auto: true,
            majA: null,
        });
        onWillStart(() => this.charger());
        // Le minuteur meurt avec le composant : personne ne regarde, personne
        // ne paie.
        this.minuteur = setInterval(() => {
            // Un onglet cache ne regarde rien : inutile de relire.
            if (document.hidden) {
                return;
            }
            if (this.state.auto && !this.state.chargement && !this.state.synchro) {
                this.charger();
            }
        }, INTERVALLE_MS);
        onWillUnmount(() => clearInterval(this.minuteur));
    }

    /** La fiche visee. Trois chemins la portent selon d'ou l'on vient : le
        bouton du formulaire, l'URL, ou les parametres de l'action. Les lire
        tous evite un tableau vide sans que rien ne dise pourquoi. */
    get domaineId() {
        const props = this.props || {};
        const action = props.action || {};
        const params = action.params || {};
        return props.resId || action.res_id || params.resId || false;
    }

    async charger() {
        this.state.erreur = null;
        const id = this.domaineId;
        if (!id) {
            this.state.erreur =
                "Aucun domaine vise. Ouvrez ce tableau depuis un domaine, " +
                "ou par son bouton « Tableau de bord ».";
            this.state.chargement = false;
            return;
        }
        try {
            this.state.donnees = await this.orm.call(
                "mailcow.domain",
                "donnees_tableau_de_bord_domaine",
                [id]
            );
            this.state.majA = new Date();
        } catch (erreur) {
            this.state.erreur = erreur.message || String(erreur);
        }
        this.state.chargement = false;
    }

    get donnees() {
        return this.state.donnees || {};
    }

    get identite() {
        return this.donnees.identite || {};
    }

    get chiffres() {
        return this.donnees.chiffres || {};
    }

    get boites() {
        return this.donnees.boites || [];
    }

    get alias() {
        return this.donnees.alias || [];
    }

    /** Les alertes a traiter, les plus graves d'abord. Les simples
        informations (fiches non synchronisees) vont a part : elles ne
        demandent pas d'action et noieraient le reste. */
    get alertes() {
        return ordonnerAlertes(this.donnees.alertes).filter(
            (alerte) => alerte.gravite !== "information"
        );
    }

    get informations() {
        return ordonnerAlertes(this.donnees.alertes).filter(
            (alerte) => alerte.gravite === "information"
        );
    }

    get lienMailcow() {
        return this.donnees.mailcow_url || "";
    }

    get heureMaj() {
        return this.state.majA ? this.state.majA.toLocaleTimeString("fr-CA") : "\u2014";
    }

    get onglets() {
        return [
            { cle: "boites", libelle: "Bo\u00eetes", nombre: this.boites.length },
            { cle: "alias", libelle: "Alias", nombre: this.alias.length },
        ];
    }

    /** Le modele a ouvrir pour la ligne cliquee : sans lui, cliquer une ligne
        d'alias ouvrirait une boite mail. */
    get modeleOnglet() {
        return this.state.onglet === "alias" ? "mailcow.alias" : "mailcow.mailbox";
    }

    /** Les lignes de l'onglet courant : filtrees, puis triees. */
    get lignes() {
        const source = this.donnees[this.state.onglet] || [];
        const filtrees = filtrer(
            source,
            this.state.recherche,
            CHAMPS_RECHERCHE[this.state.onglet] || []
        );
        return this.state.tri
            ? trier(filtrees, this.state.tri.cle, this.state.tri.sens)
            : filtrees;
    }

    get nombreAffiche() {
        const total = (this.donnees[this.state.onglet] || []).length;
        return this.lignes.length === total ? `${total} lignes` : `${this.lignes.length} sur ${total}`;
    }

    /** « 9 sur 10 », ou le nombre seul quand le plafond vient du serveur :
        afficher « 9 sur 0 » se lirait « complet », soit le contraire. */
    get textePlafond() {
        return this.chiffres.boites_max
            ? `${this.chiffres.boites} sur ${this.chiffres.boites_max}`
            : `${this.chiffres.boites} bo\u00eetes`;
    }

    get pourcentagePlafond() {
        return this.chiffres.boites_max ? this.chiffres.occupation : null;
    }

    changerOnglet(cle) {
        this.state.onglet = cle;
        this.state.tri = null;
    }

    trierPar(cle) {
        this.state.tri = basculerTri(this.state.tri, cle);
    }

    marqueTri(cle) {
        if (!this.state.tri || this.state.tri.cle !== cle) {
            return "";
        }
        return this.state.tri.sens === "asc" ? " \u25b2" : " \u25bc";
    }

    /** Ouvrir la fiche : le seul geste utile devant une ligne. */
    ouvrirFiche(modele, id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: modele,
            res_id: id,
            views: [[false, "form"]],
        });
    }

    ouvrirAlerte(alerte) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: alerte.libelle,
            res_model: alerte.modele,
            domain: alerte.filtre,
            views: [
                [false, "list"],
                [false, "form"],
            ],
        });
    }

    /** Retour a la vue d'ensemble : elle remplace, elle ne s'empile pas. */
    retour() {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "mailcow_admin.dashboard",
        });
    }

    async synchroniser() {
        this.state.synchro = true;
        try {
            await this.orm.call("mailcow.domain", "action_sync_from_mailcow", [this.domaineId]);
            await this.charger();
            this.notification.add("Domaine synchronis\u00e9 depuis Mailcow.", { type: "success" });
        } catch (erreur) {
            this.notification.add(erreur.message || String(erreur), { type: "danger" });
        }
        this.state.synchro = false;
    }

    // La presentation vit dans mailcow_dashboard_utils.js, eprouvee par
    // `node --test` ; le gabarit ne peut appeler que des membres du composant.
    classeOccupation(pourcentage) {
        return classeOccupation(pourcentage);
    }

    classeGravite(gravite) {
        return classeGravite(gravite);
    }

    texteTaux(pourcentage) {
        return texteTaux(pourcentage);
    }

    taille(mo) {
        return formaterTaille(mo);
    }

    nombre(valeur) {
        return formaterNombre(valeur);
    }

    largeur(pourcentage) {
        return largeurBarre(pourcentage);
    }
}

registry.category("actions").add("mailcow_admin.dashboard_domaine", MailcowDomainDashboard);
