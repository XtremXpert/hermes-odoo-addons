# Part of the wazo_voipms Odoo module. See LICENSE for details.
"""First-setup wizard for telephony.

When NOTHING is configured yet (no trunk, no user, no ring group), the
operations dashboard offers this wizard: it creates the first trunk, the
first user (with their extension) and the first ring group — reusing the
existing provisioning actions, never re-implementing them.
"""

from odoo import fields
from odoo import models


class WazoSetupWizard(models.TransientModel):
    _name = "wazo.setup.wizard"
    _description = "Assistant de première configuration téléphonique"

    state = fields.Selection(
        selection=[
            ("trunk", "Trunk"),
            ("user", "Usager"),
            ("group", "Groupe d'appel"),
            ("done", "Terminé"),
        ],
        default="trunk",
        required=True,
    )
    # Trunk step: protocol, POP, sub-account credentials.
    protocol = fields.Selection(
        selection=[("sip", "SIP"), ("iax2", "IAX2")],
        string="Protocole",
        default="iax2",
        required=True,
        help="IAX2 traverse le NAT sans port ouvert — recommandé derrière "
        "un réseau résidentiel.",
    )
    pop_host = fields.Char(
        string="Serveur (POP)", default="montreal1.voip.ms", required=True
    )
    voipms_username = fields.Char(
        string="Identifiant SIP VoIP.ms",
        help="Laisser vide pour créer le sous-compte automatiquement.",
    )
    voipms_password = fields.Char(
        string="Mot de passe SIP VoIP.ms",
        help="Laisser vide pour qu'il soit généré au provisionnement.",
    )
    # User step.
    user_name = fields.Char(string="Nom de l'usager", required=True)
    user_extension = fields.Char(
        string="Poste",
        required=True,
        help="Dans la plage du contexte du tenant (ex. 1000-1699).",
    )
    # Group step.
    group_name = fields.Char(string="Nom du groupe", default="Accueil")
    group_extension = fields.Char(string="Poste du groupe", required=True)
    # Created records (used by the "Done" step).
    trunk_id = fields.Many2one("wazo.voipms.trunk", string="Trunk créé")
    user_id = fields.Many2one("wazo.user", string="Usager créé")
    group_id = fields.Many2one("wazo.ring.group", string="Groupe créé")

    def action_continue(self):
        """Validate the current step then move to the next one."""
        self.ensure_one()
        if self.state == "trunk":
            return self._do_trunk()
        if self.state == "user":
            return self._do_user()
        if self.state == "group":
            return self._do_group()
        return self.action_close()

    def _do_trunk(self):
        Trunk = self.env["wazo.voipms.trunk"].sudo()
        trunk = Trunk.search([("protocol", "=", self.protocol)], limit=1)
        if not trunk:
            vals = {
                "name": "Trunk %s" % self.protocol.upper(),
                "protocol": self.protocol,
                "pop_host": self.pop_host,
            }
            if self.voipms_username:
                vals["voipms_username"] = self.voipms_username
            if self.voipms_password:
                vals["voipms_password"] = self.voipms_password
            trunk = Trunk.create(vals)
        if trunk.state != "synced":
            trunk.action_provision()
        self.write({"state": "user", "trunk_id": trunk.id})
        return self._reopen()

    def _do_user(self):
        User = self.env["wazo.user"].sudo()
        user = User.create(
            {"name": self.user_name, "extension": self.user_extension}
        )
        if user.wazo_state != "synced":
            user.action_sync_wazo()
        self.write({"state": "group", "user_id": user.id})
        return self._reopen()

    def _do_group(self):
        Group = self.env["wazo.ring.group"].sudo()
        group = Group.create(
            {
                "name": self.group_name,
                "extension": self.group_extension,
                "member_ids": [(0, 0, {"user_id": self.user_id.id, "priority": 1})],
            }
        )
        if group.wazo_state != "synced":
            group.action_sync_wazo()
        self.write({"state": "done", "group_id": group.id})
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        order = ["done", "group", "user", "trunk"]
        previous = order[max(order.index(self.state) - 1, 0)]
        self.write({"state": previous})
        return self._reopen()

    def action_close(self):
        return {"type": "ir.actions.act_window_close"}

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
