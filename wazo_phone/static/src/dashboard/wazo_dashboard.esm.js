/**
 * Tableau de bord téléphonie Wazo.
 *
 * Action client OWL (``wazo_phone.dashboard``, menu « Téléphonie Wazo →
 * Tableau de bord »). Les données viennent de
 * ``wazo.cdr.get_wazo_dashboard`` : périmètre « mes appels » (poste de
 * l'utilisateur courant) pour tout le monde, périmètre « équipe » en sus
 * pour le groupe gestionnaire.
 *
 * Rendu volontairement sans dépendance graphique : les barres de la série
 * quotidienne sont du CSS — le module n'embarque pas Chart.js pour une
 * seule visualisation.
 */
import {Component, onWillStart, proxy} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

const DAY_CHOICES = [7, 30, 90];

export class WazoDashboard extends Component {
    static template = "wazo_phone.Dashboard";
    static props = {
        action: {type: Object, optional: true},
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            days: 30,
            loading: true,
            data: null,
        });
        this.dayChoices = DAY_CHOICES;
        onWillStart(() => this.reload());
    }

    /** Recharge les agrégats du backend. */
    async reload() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "wazo.cdr",
                "get_wazo_dashboard",
                [this.state.days]
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onDaysChange(ev) {
        this.state.days = Number(ev.target.value) || 30;
        await this.reload();
    }

    // ─── Accès aux données ───────────────────────────────────────────────────

    /** @returns {?Object} périmètre « mes appels » */
    get mine() {
        return this.state.data?.mine || null;
    }

    /** @returns {?Object} périmètre « équipe » (gestionnaire seulement) */
    get team() {
        return this.state.data?.team || null;
    }

    /**
     * Série quotidienne avec hauteurs de barres calculées (0-100 %).
     *
     * @param {?Object} scope
     * @returns {Array<Object>}
     */
    seriesOf(scope) {
        const series = scope?.series || [];
        const max = Math.max(...series.map((day) => day.total), 1);
        return series.map((day) => ({
            ...day,
            height: Math.round((day.total / max) * 100),
            missedHeight: Math.round((day.missed / max) * 100),
        }));
    }

    /** @returns {String} */
    formatSeconds(seconds) {
        const total = Math.floor(seconds || 0);
        const minutes = Math.floor(total / 60);
        const hours = Math.floor(minutes / 60);
        if (hours) {
            return `${hours} h ${String(minutes % 60).padStart(2, "0")} min`;
        }
        if (minutes) {
            return `${minutes} min ${String(total % 60).padStart(2, "0")} s`;
        }
        return `${total} s`;
    }

    /** @returns {String} */
    formatDay(isoDay) {
        const date = new Date(isoDay);
        return isNaN(date.getTime())
            ? isoDay
            : date.toLocaleDateString(undefined, {day: "numeric", month: "short"});
    }

    /** @returns {String} */
    formatDateTime(iso) {
        const date = iso ? new Date(iso) : null;
        return date && !isNaN(date.getTime()) ? date.toLocaleString() : "—";
    }

    /** @returns {String} étiquette du taux de réponse d'un périmètre */
    answerRate(scope) {
        if (!scope || !scope.inbound) {
            return "—";
        }
        return `${Math.round(((scope.inbound - scope.missed) / scope.inbound) * 100)} %`;
    }

    // ─── Navigation ──────────────────────────────────────────────────────────

    /**
     * Ouvre le journal d'appels filtré sur le périmètre.
     *
     * @param {String} scope ``mine`` | ``team``
     * @param {Boolean} missedOnly ne garder que les entrants manqués
     */
    openCdrs(scope, missedOnly = false) {
        const domain = [["date_start", ">=", this._sinceIso()]];
        if (scope === "mine" && this.state.data?.extension) {
            domain.push("|", ["caller_num", "=", this.state.data.extension]);
            domain.push(["destination_num", "=", this.state.data.extension]);
        }
        if (missedOnly) {
            domain.push(["call_direction", "=", "inbound"], ["answered", "=", false]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: missedOnly ? _t("Appels manqués") : _t("Journal d'appels"),
            res_model: "wazo.cdr",
            view_mode: "list,form",
            domain,
        });
    }

    /** Ouvre la fiche contact d'un appel/agent. */
    openPartner(partnerId) {
        if (!partnerId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: partnerId,
            view_mode: "form",
            views: [[false, "form"]],
        });
    }

    /** Ouvre un CDR en formulaire. */
    openCdr(cdrId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "wazo.cdr",
            res_id: cdrId,
            view_mode: "form",
            views: [[false, "form"]],
        });
    }

    _sinceIso() {
        const since = new Date();
        since.setUTCDate(since.getUTCDate() - this.state.days);
        return since.toISOString().slice(0, 19).replace("T", " ");
    }
}

registry.category("actions").add("wazo_phone.dashboard", WazoDashboard);
