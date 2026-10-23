/**
 * Tableau de bord du serveur Wazo — vue de l'exploitant de la plateforme.
 *
 * Action client OWL (``wazo_server.dashboard``, menu « Serveur Wazo →
 * Tableau de bord »). Les données viennent de
 * ``wazo.server.dashboard.get_server_dashboard`` : tenants hébergés,
 * trunk SIP du pont VoIP.ms, routage des DIDs, et solde du fournisseur
 * — ce dernier **sur demande seulement**, pour ne pas appeler l'API à
 * chaque affichage (même principe que le tableau de bord Mailcow).
 *
 * Règles OWL 3 apprises dans ce dépôt : l'état réactif se fabrique avec
 * « proxy », le gabarit qualifie par « this. », et on rend avec « t-out ».
 */
import {Component, onWillStart, proxy} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

export class WazoServerDashboard extends Component {
    static template = "wazo_server.Dashboard";
    static props = {
        action: {type: Object, optional: true},
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            loading: true,
            checking: null,
            balanceLoading: false,
            data: null,
        });
        onWillStart(() => this.reload());
    }

    /** Recharge les agrégats locaux (aucun appel au fournisseur). */
    async reload() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "wazo.server.dashboard",
                "get_server_dashboard"
            );
        } finally {
            this.state.loading = false;
        }
    }

    /** Relit le solde VoIP.ms au près du fournisseur — geste explicite. */
    async refreshBalance() {
        this.state.balanceLoading = true;
        try {
            const data = await this.orm.call(
                "wazo.server.dashboard",
                "get_server_dashboard",
                [],
                {with_balance: true}
            );
            this.state.data = data;
        } finally {
            this.state.balanceLoading = false;
        }
    }

    /** Vérifie l'enregistrement SIP d'un trunk, puis rafraîchit la vue. */
    async checkRegistration(trunk) {
        this.state.checking = trunk.id;
        try {
            await this.orm.call(
                "wazo.voipms.trunk",
                "action_check_registration",
                [[trunk.id]]
            );
            await this.reload();
        } finally {
            this.state.checking = null;
        }
    }

    // ─── Accès aux données ───────────────────────────────────────────────────

    get tenants() {
        return this.state.data?.tenants || null;
    }

    get trunks() {
        return this.state.data?.trunks || null;
    }

    get dids() {
        return this.state.data?.dids || null;
    }

    get balance() {
        return this.state.data?.balance || null;
    }

    // ─── Navigation ───────────────────────────────────────────────────────────

    openTenants() {
        this.action.doAction("wazo_server.action_wazo_server_tenant");
    }

    openTrunks() {
        this.action.doAction("wazo_voipms.action_wazo_voipms_trunk");
    }

    /** DIDs muets : ceux qui sonnent dans le vide (sys:hangup). */
    openMutedDids() {
        this.openDids([["wazo_route_state", "!=", "routed"]]);
    }

    openDids(domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "voipms.did",
            name: "DIDs",
            views: [[false, "list"], [false, "form"]],
            domain: domain || [],
        });
    }

    // ─── Formatage ────────────────────────────────────────────────────────────

    /** Libellé du bouton d'enregistrement — l'apostrophe n'entre pas
     * dans le gabarit : l'y échapper ferait du JS bancal. */
    checkLabel(trunk) {
        return this.state.checking == trunk.id
            ? "Vérification…"
            : "Vérifier l'enregistrement";
    }

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
                  year: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
              });
    }
}

registry.category("actions").add("wazo_server.dashboard", WazoServerDashboard);
