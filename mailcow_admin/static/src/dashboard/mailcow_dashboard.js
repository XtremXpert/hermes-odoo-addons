/** @odoo-module **/
/* Tableau de bord Mailcow — lecture seule.

   Deux regles d'OWL 3, qui ont coute un plantage en production :

   1. L'etat reactif se fabrique avec « proxy », pas avec un objet litteral.
      C'est ce proxy qui forme la portee du gabarit : un objet simple y reste
      invisible, et le gabarit lit alors « chargement » sur undefined.
      Mesure sur ce client web : 119 composants sur 120 font ainsi.

   2. Dans un gabarit, tout ce qui appartient au composant se qualifie par
      « this. » : this.state, this.totaux, this.domaines, this.classeOccupation.
      Mesure : 225 gabarits qualifies, 19 non qualifies.

   useState et les references nues sont de l'OWL 2. La couche
   owl2/owl3_compatibility_layer.js fait tourner du code OWL 2 sur OWL 3, mais
   ce composant, lui, est ecrit directement en OWL 3.

   Le calcul reste cote serveur : voir mailcow.domain.donnees_tableau_de_bord. */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy } from "@odoo/owl";

export class MailcowDashboard extends Component {
    static template = "mailcow_admin.Dashboard";

    setup() {
        this.orm = useService("orm");
        // proxy, et non un objet litteral : en OWL 3 c'est cet etat reactif
        // qui forme la portee du gabarit. Un objet simple reste invisible au
        // gabarit, qui lit alors « chargement » sur undefined. C'est la cause
        // exacte du plantage « Cannot read properties of undefined ».
        this.state = proxy({ chargement: true, donnees: null, erreur: null });
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
