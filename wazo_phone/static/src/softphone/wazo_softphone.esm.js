/**
 * Composant UI du softphone Wazo (P3.3 / P3.3b).
 *
 * Affiché comme un overlay (monté par ``WazoSoftphoneApp``). Contenu : bandeau
 * d'état (Prêt / En appel / Appel entrant / Erreur), deux onglets :
 *   * « Appel »   — numéroteur + contrôles (Répondre / Raccrocher) et, en
 *                   appel, les commandes du cœur : hold/reprise, DTMF, transfert ;
 *   * « Journal » — journal d'appels (CDR) de l'utilisateur.
 *
 * Se dégrade proprement si le client SIP.js n'est pas chargé ou si l'utilisateur
 * n'a pas d'endpoint Wazo : on affiche un message clair à la place des contrôles.
 *
 * L'état réactif vient de deux sources — le **service**, qui est déjà réactif
 * (il rend ``proxy(this)``), et l'état **local** du composant (``proxy``).
 * Aucun rendu manuel n'est donc nécessaire : ``@web/owl2/utils.render`` est
 * déprécié et re-rendait le composant avec un contexte hérité, où les membres
 * posés dans ``setup()`` sont invisibles.
 */
import {Component, onMounted, proxy, t, useProps, useRef} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

const DTMF_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];

export class WazoSoftphone extends Component {
    static template = "wazo_phone.Softphone";
    props = useProps({
        target: t.string().optional(""),
    });

    setup() {
        this.service = useService("wazo_softphone");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.postCallNote = useRef("postCallNote");
        this.state = proxy({
            target: this.props.target || "",
            dtmfTones: "",
            transferTarget: "",
            activeTab: "call",
        });
        // Journal d'appels : chargé à l'ouverture, rechargé à chaque
        // bascule vers l'onglet « Journal » et à la fin d'un appel.
        onMounted(() => {
            this.service.loadCallLog();
        });
    }

    // ─── État ──────────────────────────────────────────────────────────────────

    /** @returns {Boolean} */
    get isUsable() {
        return this.service.engineAvailable && this.service.isConfigured;
    }

    /** @returns {String} */
    get statusIcon() {
        switch (this.service.state) {
            case "registered":
                return "check_circle";
            case "ringing":
                return "phone_in_talk";
            case "in_call":
                return "phone";
            case "outbound":
                return "phone";
            case "error":
                return "warning";
            default:
                return "circle";
        }
    }

    /** @returns {String} */
    get statusText() {
        if (!this.service.engineAvailable) {
            return _t("Moteur téléphonique non chargé");
        }
        if (!this.service.isConfigured) {
            return _t("Aucun endpoint Wazo pour cet utilisateur");
        }
        return this.service.status.message || _t("Prêt");
    }

    /** @returns {Boolean} */
    get isRinging() {
        return this.service.state === "ringing";
    }

    /** @returns {Boolean} */
    get isInCall() {
        return this.service.state === "in_call";
    }

    /** @returns {Boolean} */
    get isOutbound() {
        return this.service.state === "outbound";
    }

    /** @returns {Boolean} */
    get isHeld() {
        return this.service.status.held;
    }

    /** @returns {String} */
    get caller() {
        return (
            this.service.config?.display_name || this.service.config?.extension || ""
        );
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
        if (!this.state.target) {
            return;
        }
        await this.service.callOut(this.state.target);
    }

    async onAnswer() {
        await this.service.answer();
    }

    async onHangup() {
        await this.service.hangup();
    }

    /** Note post-appel : la dépose sur la fiche du contact identifié. */
    async onPostCallSave() {
        const postCall = this.service.postCall;
        const note = this.postCallNote && this.postCallNote.el.value.trim();
        if (!postCall || !note) {
            return;
        }
        await this.orm.call("res.users", "post_wazo_call_note", [
            [],
            postCall.partnerId,
            note,
            postCall.num,
        ]);
        this.service.dismissPostCall();
        this.notification.add(_t("Note consignée sur %(partner)s", {
            partner: postCall.partnerName,
        }), {type: "success"});
    }

    onTargetInput(ev) {
        this.state.target = ev.target.value;
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
        this.state.dtmfTones = ev.target.value;
    }

    onDtmfKey(key) {
        this.state.dtmfTones = (this.state.dtmfTones + key).slice(-12);
    }

    async onSendDtmf(ev) {
        if (ev) {
            ev.preventDefault();
        }
        if (!this.state.dtmfTones) {
            return;
        }
        await this.service.sendDtmf(this.state.dtmfTones);
        this.state.dtmfTones = "";
    }

    onTransferInput(ev) {
        this.state.transferTarget = ev.target.value;
    }

    async onTransfer(ev) {
        if (ev) {
            ev.preventDefault();
        }
        if (!this.state.transferTarget) {
            return;
        }
        await this.service.transfer(this.state.transferTarget);
        this.state.transferTarget = "";
    }

    // ─── Actions (onglets / journal) ───────────────────────────────────────────

    onTabChange(tab) {
        this.state.activeTab = tab;
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
