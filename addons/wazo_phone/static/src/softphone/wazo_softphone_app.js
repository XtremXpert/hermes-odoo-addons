/**
 * Main component du softphone Wazo (P3.3).
 *
 * Un composant « main » est monté par le web client au démarrage. Celui-ci :
 *
 * 1. Enregistre un item dans le **systray** (bouton téléphone).
 * 2. Gère le **cycle de vie de l'overlay** softphone : le softphone est affiché
 *    comme un overlay (au-dessus des autres overlays, comme dans le module
 *    Enterprise ``voip``), pas comme un patch de Discuss.
 *
 * C'est l'équivalent minimal du trio Enterprise
 * (``voip_service`` + ``SoftphoneContainer`` + ``VoipSystrayItem``).
 */
import {
    Component,
    onMounted,
    onPatched,
    onWillDestroy,
    useListener,
    useProps,
    xml,
    proxy,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { WazoSoftphone } from "./wazo_softphone";
import { WazoSystrayItem } from "./wazo_systray_item";

export class WazoSoftphoneApp extends Component {
    static template = xml`<t/>`;
    props = useProps({});

    setup() {
        this.service = useService("wazo_softphone");
        this.overlay = useService("overlay");
        this.softphone = proxy(this.service);
        this.prevShouldBeOnTop = false;

        // 1. Item systray.
        registry.category("systray").add("wazo_softphone", {
            Component: WazoSystrayItem,
        });

        // Le service émet ``display_changed`` à chaque show/hide : on resynchronise
        // l'overlay réel dès que l'état affiché change (pas de hook de rendu dédié).
        useListener(this.service.bus, "display_changed", () => this._applyOverlayState());
        useListener(this.service.bus, "state_changed", () => this._applyOverlayState());
        onMounted(() => this._applyOverlayState());
        onPatched(() => this._applyOverlayState());
        onWillDestroy(() => this._hideSoftphone());
    }

    /**
     * Synchronise l'état affiché (``service.isDisplayed``) avec l'overlay réel.
     */
    _applyOverlayState() {
        const isDisplayed = this.softphone.isDisplayed;
        const shouldBeOnTop = this.softphone.shouldBeOnTop;
        if (!isDisplayed) {
            this._hideSoftphone();
        } else if (!this.isShown) {
            this._showSoftphone();
        } else if (shouldBeOnTop && !this.prevShouldBeOnTop) {
            // Promotion en tête : on masque puis on re-montre.
            this._hideSoftphone();
            this._showSoftphone();
        }
        this.prevShouldBeOnTop = shouldBeOnTop;
    }

    /** @returns {boolean} */
    get isShown() {
        return Boolean(this._doHideSoftphone);
    }

    _showSoftphone() {
        if (this.isShown) {
            return;
        }
        this._doHideSoftphone = this.overlay.add(WazoSoftphone, {});
    }

    _hideSoftphone() {
        if (!this.isShown) {
            return;
        }
        this._doHideSoftphone();
        this._doHideSoftphone = undefined;
    }
}

registry.category("main_components").add("wazo_phone.SoftphoneApp", {
    Component: WazoSoftphoneApp,
});