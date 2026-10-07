/**
 * Item systray du softphone Wazo (P3.3).
 *
 * Bouton téléphone dans la barre système (systray). Ouvre/ferme le softphone
 * (overlay) et affiche l'état (Prêt, En appel, Appel entrant…).
 */
import {Component, onWillStart, useProps} from "@odoo/owl";
import {useCommand} from "@web/core/commands/command_hook";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

export class WazoSystrayItem extends Component {
    static template = "wazo_phone.SystrayItem";
    props = useProps({});

    setup() {
        this.service = useService("wazo_softphone");
        this.ui = useService("ui");
        // Pas de rendu manuel : le service est réactif (``proxy(this)``), donc
        // les getters lus par le gabarit (``state``, ``engineAvailable``…)
        // abonnent le composant d'eux-mêmes. L'ancien appel à
        // ``@web/owl2/utils.render`` était déprécié et re-rendait avec un
        // contexte hérité.
        onWillStart(async () => {
            // Charge la config à l'ouverture du premier élément.
            await this.service.loadConfig();
        });
        useCommand(_t("Basculer le softphone"), () => this.service.toggleSoftphone(), {
            hotkey: "Alt+Shift+S",
        });
    }

    /** @returns {String} */
    get icon() {
        // Un appel entrant doit se voir : une enveloppe (``o_icon_email``,
        // hérité d'un copier-coller) affichait une icône de courriel pendant
        // que le téléphone sonnait.
        return this.service.state === "ringing" ? "phone_in_talk" : "phone";
    }

    /** @returns {Boolean} */
    get hasOngoingCall() {
        return ["in_call", "outbound"].includes(this.service.state);
    }

    /** @returns {String} */
    get buttonClasses() {
        const classes = [];
        if (this.service.state === "ringing" || this.hasOngoingCall) {
            classes.push("text-success");
        }
        if (!this.service.engineAvailable) {
            classes.push("opacity-50");
        }
        return classes.join(" ");
    }

    /** @returns {String} */
    get titleText() {
        if (!this.service.engineAvailable) {
            return _t("Softphone Wazo (moteur non chargé)");
        }
        switch (this.service.state) {
            case "registered":
                return _t("Softphone prêt — cliquer pour appeler");
            case "ringing":
                return _t("Appel entrant");
            case "in_call":
                return _t("En appel");
            case "error":
                return this.service.status.message || _t("Erreur softphone");
            default:
                return _t("Softphone Wazo");
        }
    }

    onClick() {
        this.service.toggleSoftphone();
    }
}
