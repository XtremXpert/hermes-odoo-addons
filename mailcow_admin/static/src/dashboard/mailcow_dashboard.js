/** @odoo-module **/
/* Tableau de bord Mailcow.

   Regles d'OWL 3, apprises a la dure sur ce meme fichier :

   1. L'etat reactif se fabrique avec « proxy », pas avec un objet litteral :
      c'est ce proxy qui forme la portee du gabarit.
   2. Dans un gabarit, tout ce qui appartient au composant se qualifie par
      « this. ».

   Toutes les regles metier vivent cote serveur, dans
   mailcow.domain.donnees_tableau_de_bord : quelles boites sont dormantes,
   quels domaines sont au plafond, quel filtre ouvrir. Le composant affiche
   et navigue, il ne decide rien. */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy } from "@odoo/owl";

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
        });
        onWillStart(() => this.charger());
    }

    async charger() {
        this.state.erreur = null;
        try {
            this.state.donnees = await this.orm.call(
                "mailcow.domain",
                "donnees_tableau_de_bord",
                []
            );
        } catch (erreur) {
            this.state.erreur = erreur.message || String(erreur);
        }
        this.state.chargement = false;
    }

    get donnees() {
        return this.state.donnees || {};
    }

    get domaines() {
        return this.donnees.domaines || [];
    }

    /** Seules les alertes non vides meritent une carte : le serveur les renvoie
        toutes, y compris a zero, pour rester testable. */
    get alertes() {
        return (this.donnees.alertes || []).filter((alerte) => alerte.nombre > 0);
    }

    get totaux() {
        return this.donnees.totaux || {};
    }

    get grosses() {
        return this.donnees.grosses_boites || [];
    }

    get dormantes() {
        return this.donnees.dormantes || [];
    }

    /** La classe de la barre, selon la part du plafond deja consommee. */
    classeOccupation(pourcentage) {
        if (pourcentage >= 80) {
            return "progress-bar bg-danger";
        }
        return pourcentage >= 60 ? "progress-bar bg-warning" : "progress-bar bg-success";
    }

    /** Une alerte porte la gravite en clair : « danger », « attention ». */
    classeGravite(gravite) {
        if (gravite === "danger") {
            return "text-bg-danger";
        }
        return gravite === "attention" ? "text-bg-warning" : "text-bg-secondary";
    }

    /** Ouvrir la liste filtree que l'alerte designe : c'est le seul geste utile
        devant un chiffre qui derange. */
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

    /** Tirer l'etat du serveur, puis relire : un bouton, jamais un minuteur. */
    async synchroniser() {
        this.state.synchro = true;
        try {
            await this.orm.call("mailcow.domain", "action_sync_all_from_mailcow", []);
            await this.charger();
            this.notification.add("Synchronise depuis Mailcow.", { type: "success" });
        } catch (erreur) {
            this.notification.add(erreur.message || String(erreur), { type: "danger" });
        }
        this.state.synchro = false;
    }
}

registry.category("actions").add("mailcow_admin.dashboard", MailcowDashboard);
