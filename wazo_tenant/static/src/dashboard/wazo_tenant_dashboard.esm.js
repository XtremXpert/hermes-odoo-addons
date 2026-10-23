/**
 * Tableau de bord d'exploitation du tenant Wazo.
 *
 * Action client OWL (``wazo_tenant.dashboard``, menu « Téléphonie Wazo →
 * Exploitation »). Les données viennent de
 * ``wazo.tenant.dashboard.get_tenant_dashboard`` : santé des
 * synchronisations (usagers, groupes d'appel), activité des 7 derniers
 * jours, fraîcheur du journal d'appels. Tout est lu dans l'état local
 * d'Odoo — aucun appel vers Wazo au chargement.
 *
 * Règles OWL 3 du dépôt : état par « proxy », gabarit qualifié par
 * « this. », rendu par « t-out ».
 */
import {Component, onWillStart, proxy, useProps} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {standardActionServiceProps} from "@web/webclient/actions/action_plugin";

export class WazoTenantDashboard extends Component {
    static template = "wazo_tenant.Dashboard";
    // Owl 3 : les props d'une action client doivent être déclarées via
    // useProps — un « static props » fait planter le composant au chargement.
    props = useProps({...standardActionServiceProps});

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            loading: true,
            data: null,
        });
        onWillStart(() => this.reload());
    }

    /** Recharge les agrégats locaux (aucun appel au PBX). */
    async reload() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "wazo.tenant.dashboard", "get_tenant_dashboard", []);
        } finally {
            this.state.loading = false;
        }
    }

    // ─── Accès aux données ───────────────────────────────────────────────────

    get users() {
        return this.state.data?.users || null;
    }

    get groups() {
        return this.state.data?.groups || null;
    }

    get calls() {
        return this.state.data?.calls || null;
    }

    // ─── Navigation ──────────────────────────────────────────────────────────

    openUsers(domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "wazo.user",
            name: "Utilisateurs",
            views: [[false, "list"], [false, "form"]],
            domain: domain || [],
        });
    }

    openUsersInError() {
        this.openUsers([["wazo_state", "!=", "synced"]]);
    }

    openGroups(domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "wazo.ring.group",
            name: "Groupes d'appel",
            views: [[false, "list"], [false, "form"]],
            domain: domain || [],
        });
    }

    openCalls(domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "wazo.cdr",
            name: "Journal d'appels",
            views: [[false, "list"], [false, "form"]],
            domain: domain || [],
        });
    }

    openMissed() {
        this.openCalls([["answered", "=", false]]);
    }

    // ─── Formatage ────────────────────────────────────────────────────────────

    formatDateTime(iso) {
        if (!iso) {
            return "—";
        }
        const date = new Date(iso);
        return isNaN(date.getTime())
            ? iso
            : date.toLocaleString(undefined, {
                  day: "numeric",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
              });
    }

    formatSeconds(seconds) {
        const total = Math.floor(seconds || 0);
        const minutes = Math.floor(total / 60);
        if (minutes) {
            return `${minutes} min ${String(total % 60).padStart(2, "0")} s`;
        }
        return `${total} s`;
    }

    directionLabel(direction) {
        return {outbound: "→", inbound: "←", internal: "↔"}[direction] || "·";
    }
}

registry.category("actions").add("wazo_tenant.dashboard", WazoTenantDashboard);
