# Part of the proxmox_tenant Odoo module. See LICENSE for details.
"""Ce que les objets Proxmox partagent : perimetre, groupes, sync a la vue."""

import logging

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import AccessError
from odoo.exceptions import UserError

from ..services.proxmox_client import ProxmoxAPIError

_logger = logging.getLogger(__name__)

RAFRAICHISSEMENT_MIN_S = 60


class ProxmoxSyncMixin(models.AbstractModel):
    _name = "proxmox.sync.mixin"
    _inherit = ["mail.thread"]
    _description = "Proxmox : suivi de synchronisation"

    last_synced_on = fields.Datetime(string="Dernière synchronisation", readonly=True)

    @api.model
    def _exiger(self, groupe):
        """Refuser l'appel à qui n'a pas le groupe, AVANT tout appel au serveur."""
        if self.env.su or self.env.user.has_group("proxmox_tenant.group_proxmox_" + groupe):
            return
        nom = {
            "manager": "Gestionnaire",
            "user": "Utilisateur",
            "sync": "Lecture et synchronisation",
        }[groupe]
        raise AccessError(self.env._("Action Proxmox réservée au groupe %s.", nom))

    def _journaliser(self, corps):
        """Noter dans le fil de la fiche ce qui vient d'être fait sur Proxmox."""
        for fiche in self:
            fiche.message_post(body=corps, subtype_xmlid="mail.mt_note")

    @api.model
    def _pools_autorises(self):
        """Le périmètre des pools du tenant, ou None si le cluster entier.

        ``proxmox.allowed_pools`` porte une liste séparée par des virgules :
        ``diverse`` pour un tenant, vide chez l'opérateur — qui voit tout le
        cluster. Une instance tenant ne doit jamais rapatrier les machines
        d'un autre pool.
        """
        brut = self.env["ir.config_parameter"].sudo().get_str("proxmox.allowed_pools", "")
        autorises = {p.strip() for p in brut.split(",") if p.strip()}
        return autorises or None

    @api.model
    def _rafraichir_si_obsolete(self):
        """Synchroniser le local depuis le serveur si la copie est vieille.

        Appelée à l'ouverture de chaque vue : l'horodatage par modèle borne
        la fréquence à ``RAFRAICHISSEMENT_MIN_S``. Une erreur du serveur ne
        casse pas l'écran — le dernier état connu s'affiche.
        """
        icp = self.env["ir.config_parameter"].sudo()
        cle = "proxmox.%s.last_refresh" % self._name
        brut = icp.get_str(cle, "")
        if brut:
            ecoule = (fields.Datetime.now() - fields.Datetime.to_datetime(brut)).total_seconds()
            if ecoule < RAFRAICHISSEMENT_MIN_S:
                return
        try:
            self.env[self._name].sudo()._sync_all_from_proxmox()
            icp.set_str(cle, fields.Datetime.to_string(fields.Datetime.now()))
        except (UserError, ProxmoxAPIError) as erreur:
            _logger.warning("Sync %s au chargement de vue : %s", self._name, erreur)

    def web_search_read(
        self, domain, specification, offset=0, limit=None, order=None, count_limit=None
    ):
        self._rafraichir_si_obsolete()
        return super().web_search_read(
            domain,
            specification,
            offset=offset,
            limit=limit,
            order=order,
            count_limit=count_limit,
        )
