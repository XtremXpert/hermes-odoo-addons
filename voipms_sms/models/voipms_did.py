# Part of the voipms_sms Odoo module. See LICENSE for details.
"""DID : numéro d'émetteur de SMS (appartenant au compte VoIP.ms)."""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..services.sms_segmentation import normalize_nanp
from ..services.voipms_client import VoIPMSClient


class VoIPMSDid(models.Model):
    _name = "voipms.did"
    _description = "VoIP.ms : DID (numéro d'émetteur)"
    _order = "number"

    number = fields.Char(string="Numéro", required=True)
    label = fields.Char(string="Étiquette")
    sms_available = fields.Boolean(string="SMS disponible")
    sms_enabled = fields.Integer(string="SMS activé", default=0, help="0 = désactivé, 1 = activé")
    synced = fields.Boolean(string="Synchronisé avec VoIP.ms")
    active = fields.Boolean(string="Actif", default=True)

    _number_uniq = models.Constraint("unique(number)", "Ce numéro existe déjà.")

    @api.model_create_multi
    def create(self, vals_list):
        """Crée des DID en normalisant leur numéro et en refusant les doublons.

        Args:
            vals_list: liste des dictionnaires de valeurs des DID.

        Returns:
            recordset: les DID créés.

        Raises:
            UserError: si un numéro n'est pas NANP ou existe déjà.
        """
        for vals in vals_list:
            try:
                number = normalize_nanp(vals.get("number") or "")
            except ValueError as error:
                raise UserError(str(error)) from error
            if self.search([("number", "=", number)], limit=1):
                raise UserError(self.env._("Le numéro %s existe déjà.", number))
            vals["number"] = number
        return super().create(vals_list)

    @api.model
    def _get_dids_info(self):
        """Return the DID entries from the provider.

        The current API answers with ``dids``; older answers used ``did``.
        """
        response = VoIPMSClient(self.env)._request("getDIDsInfo")
        return response.get("dids") or response.get("did") or []

    @api.model
    def sync_from_provider(self):
        """Create or update the DID records from the VoIP.ms account.

        Model-level on purpose: the DID table is empty on a fresh database, so
        a per-record button could never start the first synchronization.
        """
        for entry in self._get_dids_info():
            if not isinstance(entry, dict) or not entry.get("did"):
                continue
            try:
                number = normalize_nanp(entry["did"])
            except ValueError:
                continue
            did = self.search([("number", "=", number)], limit=1)
            values = {
                "sms_available": bool(entry.get("sms_available")),
                "sms_enabled": int(str(entry.get("sms_enabled") or "0")),
                "synced": True,
            }
            if did:
                did.write(values)
            else:
                self.create(dict(values, number=number))
        return True

    def action_sync_from_provider(self):
        """Synchronize all DIDs from the DID form button."""
        return self.env["voipms.did"].sync_from_provider()
