/** @odoo-module **/
/* Tableau de bord Mailcow — lecture seule.

   OWL 3 : les signaux remplacent useState et reactive, absents du paquet
   livre avec cet Odoo. Ce composant n'en a pas besoin : il charge une fois,
   dans onWillStart, qui resout avant le premier rendu. Rien ne bouge ensuite,
   donc rien a rendre reactif. Le calcul, lui, reste cote serveur : voir
   mailcow.domain.donnees_tableau_de_bord. */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart } from "@odoo/owl";

export class MailcowDashboard extends Component {
    static template = "mailcow_admin.Dashboard";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.state = { chargement: true, donnees: null, erreur: null };
        onWillStart(async () => {
            try {
                this.state.donnees = await this.orm.call(
                    "mailcow.domain", "donnees_tableau_de_bord", []);
            } catch (erreur) {
                this.state.erreur = erreur.message || String(erreur);
            }
            this.state.chargement = false;
        });
    }

    get domaines() {
        return (this.state.donnees && this.state.donnees.domaines) || [];
    }

    get totaux() {
        return (this.state.donnees && this.state.donnees.totaux) || {};
    }

    get serrees() {
        return (this.state.donnees && this.state.donnees.boites_serrees) || [];
    }

    /** La classe de la barre, selon la part du plafond deja consommee. */
    classeOccupation(pourcentage) {
        if (pourcentage >= 80) {
            return "progress-bar bg-danger";
        }
        return pourcentage >= 60 ? "progress-bar bg-warning" : "progress-bar bg-success";
    }
}

registry.category("actions").add("mailcow_admin.dashboard", MailcowDashboard);
