/**
 * Composant UI du softphone Wazo (P3.3 / P3.3b).
 *
 * Affiché comme un overlay (monté par ``WazoSoftphoneApp``). Contenu :
 * bandeau d'état (Prêt / En appel / Appel entrant / Erreur), deux onglets :
 *   * « Appel »   — numéroteur + contrôles (Répondre / Raccrocher) et, en
 *                   appel, les commandes du cœur : hold/reprise, DTMF, transfert ;
 *   * « Journal » — journal d'appels (CDR) de l'utilisateur.
 *
 * Se dégrade proprement si le client SIP.js n'est pas chargé ou si l'utilisateur
 * n'a pas d'endpoint Wazo : on affiche un message clair à la place des contrôles.
 */
import { Component, onWillUpdateProps, onMounted, useListener } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { render } from "@web/owl2/utils";

const DTMF_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];

export class WazoSoftphone extends Component {
    static props = {
        target: { type: String, optional: true, default: () => "" },
    };
    static template = "wazo_phone.Softphone";

    setup() {
        this.service = useService("wazo_softphone");
        this.target = this.props.target || "";
        this.dtmfTones = "";
        this.transferTarget = "";
        this.activeTab = "call";
        useListener(this.service.bus, "state_changed", () => render(this, true));
        useListener(this.service.bus, "display_changed", () => render(this, true));
        // Journal d'appels : chargé à l'ouverture, rechargé à chaque
        // bascule vers l'onglet « Journal » et à la fin d'un appel.
        onMounted(() => {
            this.service.loadCallLog();
        });
        onWillUpdateProps(() => [
            this.service.status.state,
            this.service.status.message,
            this.service.status.held,
            this.service.callLog,
            this.service.isConfigured,
            this.service.engineAvailable,
        ]);
    }

    // ─── État ──────────────────────────────────────────────────────────────────

    /** @returns {boolean} */
    get isUsable() {
        return this.service.engineAvailable && this.service.isConfigured;
    }

    /** @returns {string} */
    get statusIcon() {
        switch (this.service.state) {
            case "registered":
                return "fa-check-circle";
            case "ringing":
                return "fa-phone-volume";
            case "in_call":
                return "fa-phone";
            case "outbound":
                return "fa-phone-square";
            case "error":
                return "fa-exclamation-triangle";
            default:
                return "fa-circle";
        }
    }

    /** @returns {string} */
    get statusText() {
        if (!this.service.engineAvailable) {
            return _t("Moteur téléphonique non chargé");
        }
        if (!this.service.isConfigured) {
            return _t("Aucun endpoint Wazo pour cet utilisateur");
        }
        return this.service.status.message || _t("Prêt");
    }

    /** @returns {boolean} */
    get isRinging() {
        return this.service.state === "ringing";
    }

    /** @returns {boolean} */
    get isInCall() {
        return this.service.state === "in_call";
    }

    /** @returns {boolean} */
    get isOutbound() {
        return this.service.state === "outbound";
    }

    /** @returns {boolean} */
    get isHeld() {
        return this.service.status.held;
    }

    /** @returns {string} */
    get caller() {
        return this.service.config?.display_name || this.service.config?.extension || "";
    }

    /** @returns {Array<Object>} Journal d'appels (plus récent d'abord). */
    get callLog() {
        return this.service.callLog || [];
    }

    /** @returns {Array<string>} Touches DTMF (affichées dans le pavé). */
    get dtmfKeys() {
        return DTMF_KEYS;
    }

    // ─── Actions (appel) ───────────────────────────────────────────────────────

    async onCall(ev) {
        ev.preventDefault();
        if (!this.target) {
            return;
        }
        await this.service.callOut(this.target);
    }

    async onAnswer() {
        await this.service.answer();
    }

    async onHangup() {
        await this.service.hangup();
    }

    onTargetInput(ev) {
        this.target = ev.target.value;
    }

    // ─── Actions (cœur d'appel : hold / DTMF / transfert) ──────────────────────

    async onHoldToggle() {
        if (this.isHeld) {
            await this.service.unhold();
        } else {
            await this.service.hold();
        }
    }

    onDtmfInput(ev) {
        this.dtmfTones = ev.target.value;
    }

    onDtmfKey(key) {
        this.dtmfTones = (this.dtmfTones + key).slice(-12);
    }

    async onSendDtmf(ev) {
        if (ev) {
            ev.preventDefault();
        }
        if (!this.dtmfTones) {
            return;
        }
        await this.service.sendDtmf(this.dtmfTones);
        this.dtmfTones = "";
    }

    onTransferInput(ev) {
        this.transferTarget = ev.target.value;
    }

    async onTransfer(ev) {
        if (ev) {
            ev.preventDefault();
        }
        if (!this.transferTarget) {
            return;
        }
        await this.service.transfer(this.transferTarget);
        this.transferTarget = "";
    }

    // ─── Actions (onglets / journal) ───────────────────────────────────────────

    onTabChange(tab) {
        this.activeTab = tab;
        if (tab === "log") {
            this.service.loadCallLog();
        }
    }

    formatDuration(seconds) {
        if (seconds === undefined || seconds === null) {
            return "—";
        }
        const s = Math.floor(seconds % 60);
        const m = Math.floor((seconds / 60) % 60);
        const h = Math.floor(seconds / 3600);
        const pad = (n) => String(n).padStart(2, "0");
        return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
    }

    formatDateTime(iso) {
        if (!iso) {
            return "—";
        }
        const d = new Date(iso);
        return isNaN(d.getTime()) ? "—" : d.toLocaleString();
    }

    onClose() {
        this.service.hideSoftphone();
    }
}