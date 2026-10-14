/* Copyright 2026 Bemade Inc., Benoît Vézina — AGPL-3
 *
 * Boutons d'approbation de Hermes : envoi sans recharger la page.
 * Repris de hermes_boutons (mac-demo). Le corps d'un message Discuss est du
 * HTML rendu par t-out, pas des composants : on patche Message pour câbler,
 * une fois le corps monté, les liens marqués « o_hermes_approve » (posés par
 * models/formatting.py).
 *
 * Le clic passe par /hermes/approbation en JSON-RPC (POST, corps JSON), jamais
 * par le GET du lien : voir controllers/main.py. Sans ce script, le lien mène
 * à une page de confirmation, la commande reste aussi écrite sous les boutons.
 */
import {Message} from "@mail/core/common/message";
import {patch} from "@web/core/utils/patch";
import {rpc} from "@web/core/network/rpc";
import {useEffect} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

patch(Message.prototype, {
    setup() {
        super.setup();
        this.hermesNotification = useService("notification");
        // Owl 3 : l'effet se rejoue quand les signaux lus changent (ref du
        // corps, corps du message).
        useEffect(() => {
            const corps = this.messageBody();
            const contenu = this.message?.body;
            if (!corps || contenu === undefined) {
                return;
            }
            const boutons = corps.querySelectorAll("a.o_hermes_approve");
            if (!boutons.length) {
                return;
            }
            const onClick = async (ev) => {
                const lien = ev.currentTarget;
                const url = new URL(
                    lien.getAttribute("href") || "",
                    window.location.origin
                );
                if (url.pathname !== "/hermes/repondre") {
                    return;
                }
                ev.preventDefault();
                try {
                    await rpc("/hermes/approbation", {
                        canal: url.searchParams.get("canal"),
                        cmd: url.searchParams.get("cmd"),
                    });
                } catch {
                    // Repli : la page de confirmation.
                    window.location.href = url.href;
                    return;
                }
                const groupe = lien.closest(".o_hermes_approval");
                const selecteur = "a.o_hermes_approve";
                const figes = groupe ? groupe.querySelectorAll(selecteur) : [];
                for (const bouton of figes) {
                    bouton.style.pointerEvents = "none";
                    bouton.style.opacity = "0.5";
                }
                this.hermesNotification.add("Envoyé à Hermes.", {type: "success"});
            };
            for (const bouton of boutons) {
                bouton.addEventListener("click", onClick);
            }
            return () => {
                for (const bouton of boutons) {
                    bouton.removeEventListener("click", onClick);
                }
            };
        });
    },
});
