# Part of the wazo_server Odoo module. See LICENSE for details.
"""Agrégats du tableau de bord du serveur Wazo (exploitant de la plateforme).

Le tableau de bord croise trois sources :

* ``wazo.server.tenant`` — les clients hébergés, leur état et l'expiration
  de leurs jetons d'API ;
* ``wazo.voipms.trunk`` et ``voipms.did`` — l'état du pont téléphonique
  (trunk SIP sortant, routage des DIDs entrants), fourni par ``wazo_voipms`` ;
* le solde du compte VoIP.ms — **sur demande seulement** : le relire à
  chaque affichage ferait un appel d'API par visite, comme l'évite déjà le
  tableau de bord Mailcow pour son propre serveur. Le geste reste explicite.

L'état local d'Odoo suffit à tout le reste : les fiches du pont sont
rafraîchies par leurs propres actions (« Vérifier l'enregistrement »),
et le tableau de bord ne fait que les lire.
"""

import logging

from odoo import api
from odoo import fields
from odoo import models
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSAPIError
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient

_logger = logging.getLogger(__name__)

#: Délai d'alerte sur l'expiration des jetons de tenant (jours).
JETON_ALERTE_JOURS = 30


class WazoServerDashboard(models.AbstractModel):
    _name = "wazo.server.dashboard"
    _description = "Tableau de bord du serveur Wazo"

    def _tenant_expires_soon(self, tenant):
        """Le jeton du tenant expire-t-il dans les 30 jours ?"""
        if not tenant.token_expires_at:
            return False
        delta = tenant.token_expires_at - fields.Datetime.now()
        return delta.days <= JETON_ALERTE_JOURS

    def _voipms_balance(self):
        """Lit le solde VoIP.ms — sans jamais faire échouer le tableau.

        Retourne ``{"amount": "7.10"}`` en cas de succès, ``{"amount":
        None, "error": "…"}`` en cas d'échec (API muette, identifiants
        absents) : un fournisseur injoignable ne doit pas cacher l'état
        des trunks, qui lui est local.
        """
        try:
            client = VoIPMSClient(self.env)
            response = client._request("getBalance")
        except VoIPMSAPIError as error:
            _logger.debug("Solde VoIP.ms illisible : %s", error)
            return {"amount": None, "error": str(error)}
        balance = (response or {}).get("balance") or {}
        try:
            amount = float(balance.get("current_balance"))
        except (TypeError, ValueError):
            _logger.debug("Solde VoIP.ms illisible : %s", balance)
            return {"amount": None, "error": "Réponse sans solde exploitable."}
        return {"amount": "%.2f" % amount, "error": None}

    @api.model
    def get_server_dashboard(self, with_balance=False):
        """Tous les agrégats du tableau de bord, en un seul appel.

        ``with_balance`` relit le solde VoIP.ms au près du fournisseur —
        geste explicite du bouton « Actualiser le solde », jamais du
        chargement de la page.
        """
        Tenant = self.env["wazo.server.tenant"]
        # Trunk et DIDs lus en sudo : c'est l'état opérationnel du pont,
        # pas des données SMS — et l'exploitant de la plateforme n'a pas
        # à porter les groupes du module SMS pour surveiller sa
        # téléphonie. Le menu qui mène ici est déjà réservé au groupe
        # gestionnaire.
        Trunk = self.env["wazo.voipms.trunk"].sudo()
        Did = self.env["voipms.did"].sudo()

        tenants = Tenant.search([], order="name")
        trunks = Trunk.search([], order="name")
        dids = Did.search([], order="number")

        # Tenants : compteurs par état + alerte sur les jetons expirants.
        tenant_states = {state: 0 for state, _ in Tenant._fields["state"].selection}
        for tenant in tenants:
            tenant_states[tenant.state] = tenant_states.get(tenant.state, 0) + 1
        tenant_items = [
            {
                "id": tenant.id,
                "name": tenant.name,
                "state": tenant.state,
                "context_name": tenant.context_name or tenant.remote_context_name or "",
                "token_expires_at": tenant.token_expires_at
                and tenant.token_expires_at.isoformat(),
                "expires_soon": self._tenant_expires_soon(tenant),
            }
            for tenant in tenants
        ]

        # Trunks du pont : état de provisioning + enregistrement SIP.
        trunk_items = [
            {
                "id": trunk.id,
                "name": trunk.name,
                "state": trunk.state,
                "registered": trunk.registered,
                "pop_host": trunk.pop_host,
                "voipms_username": trunk.voipms_username,
                "error_message": trunk.error_message or "",
            }
            for trunk in trunks
        ]

        # DIDs : routés vers Wazo ou muets (sys:hangup côté VoIP.ms).
        did_items = [
            {
                "id": did.id,
                "number": did.number,
                "route_state": did.wazo_route_state,
            }
            for did in dids
        ]
        did_routed = sum(1 for did in did_items if did["route_state"] == "routed")

        return {
            "tenants": {
                "items": tenant_items,
                "total": len(tenants),
                "states": tenant_states,
                "expiring": sum(1 for item in tenant_items if item["expires_soon"]),
            },
            "trunks": {"items": trunk_items},
            "dids": {
                "items": did_items,
                "total": len(dids),
                "routed": did_routed,
                "muted": len(dids) - did_routed,
            },
            "balance": self._voipms_balance() if with_balance else None,
        }
