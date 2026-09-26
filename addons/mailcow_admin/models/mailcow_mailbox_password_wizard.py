# Part of the mailcow_admin Odoo module. See LICENSE for details.
from odoo import _
from odoo import fields
from odoo import models
from odoo.exceptions import ValidationError

from ..services.mailcow_client import MailcowClient

MISMATCH_ERROR = "Les deux mots de passe ne correspondent pas."


class MailboxPasswordWizard(models.TransientModel):
    _name = 'mailcow.mailbox.password'
    _description = "Mailcow: réinitialisation du mot de passe"

    mailbox_id = fields.Many2one(
        'mailcow.mailbox', string='Boîte mail', required=True,
        ondelete='cascade',
    )
    password = fields.Char(string='Nouveau mot de passe', required=True)
    confirm = fields.Char(string='Confirmation', required=True)

    def _check_password_match(self, password, confirm):
        if password and confirm and password != confirm:
            raise ValidationError(_(MISMATCH_ERROR))

    def create(self, vals):
        vals = vals if isinstance(vals, list) else [vals]
        for item in vals:
            self._check_password_match(item.get('password'), item.get('confirm'))
        if len(vals) == 1:
            return super().create(vals[0])
        return super().create(vals)

    def write(self, vals):
        for wizard in self:
            self._check_password_match(
                vals.get('password', wizard.password),
                vals.get('confirm', wizard.confirm),
            )
        return super().write(vals)

    def action_reset(self):
        """Pousse le nouveau mot de passe vers Mailcow."""
        self.ensure_one()
        mailbox = self.mailbox_id
        client = MailcowClient(self.env)
        # Même forme que les autres éditions : {"items": [...], "attr": {...}}.
        # Un corps plat est accepté puis ignoré, le mot de passe ne changeait donc
        # jamais malgré une réponse « success ».
        client._request('POST', '/edit/mailbox', {
            'items': [mailbox.email],
            'attr': {
                'password': self.password,
                'password2': self.password,
            },
        })
        mailbox.write({'synced': True})
        return {'type': 'ir.actions.act_window_close'}
