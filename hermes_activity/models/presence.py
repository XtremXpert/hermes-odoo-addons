"""Presence from authenticated gateway polling, with an expiring heartbeat."""

from datetime import timedelta

from odoo import api
from odoo import fields
from odoo import models

from .activity import AGENT_GROUPS
from .activity import _is_agent


class ActivityPresence(models.AbstractModel):
    _inherit = "hermes.activity"

    def _heartbeat(self):
        if _is_agent(self.env):
            # Never use _try_update_presence: it commits the caller's transaction.
            self.env["mail.presence"]._update_presence(self.env.user)

    @api.model
    def _expire_presence(self):
        groups = [
            group.id
            for name in AGENT_GROUPS
            if (group := self.env.ref(name, raise_if_not_found=False))
        ]
        users = self.env["res.users"].sudo().search([("group_ids", "in", groups)])
        cutoff = fields.Datetime.now() - timedelta(minutes=3)
        self.env["mail.presence"].sudo().search(
            [
                ("user_id", "in", users.ids),
                ("last_poll", "<", cutoff),
                ("status", "!=", "offline"),
            ]
        ).write({"status": "offline"})


class ChannelMember(models.Model):
    _inherit = "discuss.channel.member"

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        result = super().search_read(
            domain=domain, fields=fields, offset=offset, limit=limit, order=order
        )
        # The deployed gateway discovers its conversations every 60 seconds,
        # even when no human is talking to it. Only refresh the authenticated user.
        self.env["hermes.activity"]._heartbeat()
        return result
