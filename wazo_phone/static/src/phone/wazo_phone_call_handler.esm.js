/**
 * Click-to-call Wazo (bouton « Appeler » des champs téléphone).
 *
 * Le widget ``phone`` d'Odoo appelle ``callPhoneNumber``, qui consulte le
 * registre ``phone_call_handlers`` : le premier gestionnaire applicable
 * prend l'appel, sinon le lien ``tel:`` du navigateur sert de repli. Ici le
 * gestionnaire est applicable dès que le softphone de l'utilisateur est
 * configuré — l'appel part alors par son endpoint WebRTC au lieu de passer
 * la main au système.
 */
import {cleanPhoneNumber} from "@web/core/phone/phone_call";
import {registry} from "@web/core/registry";

export const wazoPhoneCallHandler = {
    /**
     * Le softphone de l'utilisateur courant est-il prêt à composer ?
     *
     * @param {import("@web/env").OdooEnv} env
     * @returns {Boolean}
     */
    isApplicable(env) {
        // The service alone decides: config may still be loading on first
        // click, so execute() awaits it rather than being gated here.
        return Boolean(env.services.wazo_softphone);
    },

    /**
     * Passe l'appel par le softphone (overlay ouvert sur la numérotation).
     *
     * @param {import("@web/env").OdooEnv} env
     * @param {Object} params ``{phoneNumber, resModel, resId}``
     * @returns {Promise<Boolean>}
     */
    async execute(env, params) {
        const service = env.services.wazo_softphone;
        const number = cleanPhoneNumber(params.phoneNumber || "");
        if (!service || !number) {
            return false;
        }
        if (!service.config) {
            await service.loadConfig();
        }
        if (!service.isConfigured) {
            // No Wazo account for this user: hand the call to the system
            // ``tel:`` link as usual.
            return false;
        }
        service.showSoftphone();
        await service.callOut(number);
        return true;
    },
};

registry.category("phone_call_handlers").add("wazo_phone", wazoPhoneCallHandler);
