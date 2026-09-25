/** @odoo-module **/
/* Tableau de bord Mailcow.

   Regles d'OWL 3, apprises a la dure sur ce meme fichier :

   1. L'etat reactif se fabrique avec « proxy », pas avec un objet litteral :
      c'est ce proxy qui forme la portee du gabarit.
   2. Dans un gabarit, tout ce qui appartient au composant se qualifie par
      « this. ».

   Le tri et le filtre vivent dans mailcow_dashboard_utils.js, sans aucune
   dependance, pour etre eprouvables par `node --test` — donc verifies a chaque
   integration continue. Le composant les appelle, il ne reimplemente rien.

   Le rafraichissement relit l'etat local d'Odoo, jamais Mailcow : un intervalle
   qui interrogerait l'API toutes les trente secondes peserait sur la
   production. Tirer l'etat du serveur reste un geste explicite. */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, proxy } from "@odoo/owl";

import { basculerTri, filtrer, trier } from "./mailcow_dashboard_utils";

const INTERVALLE_MS = 30000;
const CHAMPS_RECHERCHE = {
    domaines: ["nom", "derniere_synchro"],
    boites: ["nom", "domaine", "quota_utilise_mb", "messages"],
    alias: ["nom", "domaine", "destinations"],
};

export class MailcowDashboard extends Component {
    static template = "mailcow_admin.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            chargement: true,
            donnees: null,
            erreur: null,
            synchro: false,
            onglet: "domaines",
            recherche: "",
            tri: null,
            auto: true,
            majA: null,
        });
        onWillStart(() => this.charger());
        // Le minuteur meurt avec le composant : personne ne regarde, personne
        // ne paie. Aucune tache serveur, aucun minuteur fantome.
        this.minuteur = setInterval(() => {
            if (this.state.auto && !this.state.chargement && !this.state.synchro) {
                this.charger();
            }
        }, INTERVALLE_MS);
        onWillUnmount(() => clearInterval(this.minuteur));
    }

    async charger() {
        this.state.erreur = null;
        try {
            this.state.donnees = await this.orm.call(
                "mailcow.domain",
                "donnees_tableau_de_bord",
                []
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

    get onglets() {
        return [
            { cle: "domaines", libelle: "Domaines", nombre: this.domaines.length },
            { cle: "boites", libelle: "Bo\u00eetes", nombre: this.boites.length },
            { cle: "alias", libelle: "Alias", nombre: this.alias.length },
        ];
    }

    get domaines() {
        return this.donnees.domaines || [];
    }

    get boites() {
        return this.donnees.boites || [];
    }

    get alias() {
        return this.donnees.alias || [];
    }

    get alertes() {
        return (this.donnees.alertes || []).filter((alerte) => alerte.nombre > 0);
    }

    get totaux() {
        return this.donnees.totaux || {};
    }

    get lienMailcow() {
        return this.donnees.mailcow_url || "";
    }

    get heureMaj() {
        return this.state.majA ? this.state.majA.toLocaleTimeString("fr-CA") : "\u2014";
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

    /** Changer d'onglet remet le tri a zero : les colonnes n'ont plus rien a
        voir d'un tableau a l'autre, et garder l'ordre induirait en erreur. */
    changerOnglet(cle) {
        this.state.onglet = cle;
        this.state.tri = null;
    }

    /** Un clic sur un en-tete monte, descend, puis oublie le tri. */
    trierPar(cle) {
        this.state.tri = basculerTri(this.state.tri, cle);
    }

    /** La fleche de l'en-tete, quand c'est lui qui commande l'ordre. */
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

    async synchroniser() {
        this.state.synchro = true;
        try {
            await this.orm.call("mailcow.domain", "action_sync_all_from_mailcow", []);
            await this.charger();
            this.notification.add("Synchronis\u00e9 depuis Mailcow.", { type: "success" });
        } catch (erreur) {
            this.notification.add(erreur.message || String(erreur), { type: "danger" });
        }
        this.state.synchro = false;
    }

    classeOccupation(pourcentage) {
        if (pourcentage === null || pourcentage === undefined) {
            return "progress-bar bg-secondary";
        }
        if (pourcentage >= 80) {
            return "progress-bar bg-danger";
        }
        return pourcentage >= 60 ? "progress-bar bg-warning" : "progress-bar bg-success";
    }

    classeGravite(gravite) {
        if (gravite === "danger") {
            return "text-bg-danger";
        }
        return gravite === "attention" ? "text-bg-warning" : "text-bg-secondary";
    }

    /** « 12.5 % » ou « sans quota » : un taux absent n'est pas un zero. */
    texteTaux(pourcentage) {
        return pourcentage === null || pourcentage === undefined
            ? "sans quota"
            : pourcentage + " %";
    }
}

registry.category("actions").add("mailcow_admin.dashboard", MailcowDashboard);
