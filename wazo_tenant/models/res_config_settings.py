# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Réglages de connexion Wazo (URL, token API, tenant)."""

from odoo import fields
from odoo import models
from odoo.addons.wazo_tenant.services.wazo_client import WazoAPIError
from odoo.addons.wazo_tenant.services.wazo_client import WazoClient


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    wazo_url = fields.Char(
        string="URL du serveur Wazo",
        config_parameter="wazo.url",
        help="ex : https://wazo.diverse-cite.com",
    )
    wazo_api_key = fields.Char(string="Token API Wazo", config_parameter="wazo.api_key")
    wazo_tenant_id = fields.Char(
        string="Tenant Wazo (UUID)",
        config_parameter="wazo.tenant_id",
        help="Laisser vide pour un serveur mono-tenant.",
    )
    wazo_tenant_fk = fields.Many2one(
        "wazo.tenant",
        string="Tenant Wazo",
        compute="_compute_wazo_tenant_fk",
        inverse="_inverse_wazo_tenant_fk",
        store=False,
        help="Tenant que l'instance adresse. Un seul connu : il est retenu "
        "d'office — plusieurs : c'est le choix à faire ici.",
    )
    wazo_line_context = fields.Char(
        string="Contexte des lignes",
        config_parameter="wazo.line_context",
        help="Contexte Asterisk utilisé pour les lignes et postes (défaut : « default »).",
    )
    wazo_ssl_verify = fields.Boolean(
        string="Vérifier le certificat TLS",
        config_parameter="wazo.ssl_verify",
        help="Désactiver uniquement pour un serveur Wazo au certificat "
        "auto-signé (PBX interne). La vérification reste la règle.",
    )
    wazo_voicemail_language = fields.Char(
        string="Langue des messageries vocales",
        config_parameter="wazo.voicemail_language",
        help="ex : fr_CA, en_US (défaut : fr_CA).",
    )
    wazo_connection_ok = fields.Boolean(default=False)

    def _compute_wazo_tenant_fk(self):
        """Le tenant configuré : la fiche dont l'UUID porte le paramètre."""
        param = self.env["ir.config_parameter"].sudo().get_str("wazo.tenant_id") or ""
        for settings in self:
            settings.wazo_tenant_fk = (
                self.env["wazo.tenant"].search([("remote_uuid", "=", param)], limit=1)
                if param
                else False
            )

    def _inverse_wazo_tenant_fk(self):
        """Retient le tenant choisi — l'UUID, qui seul survit aux fiches."""
        param = self.env["ir.config_parameter"].sudo()
        for settings in self:
            param.set_str(
                "wazo.tenant_id",
                settings.wazo_tenant_fk.remote_uuid or False,
            )

    def action_sync_wazo_tenants(self):
        """Rafraîchit la liste des tenants visibles du jeton."""
        self.ensure_one()
        self.execute()
        return self.env["wazo.tenant"].action_sync_from_wazo()

    def action_test_wazo_connection(self):
        """Vérifie la connexion avec un appel en lecture seule."""
        self.ensure_one()
        self.execute()
        client = WazoClient(self.env)
        try:
            client.conf("GET", "/users", params={"limit": 1})
        except WazoAPIError as error:
            self.wazo_connection_ok = False
            raise WazoAPIError(str(error)) from error
        self.wazo_connection_ok = True
