# Part of the sms_voipms Odoo module. See LICENSE for details.
"""Route ``sms.sms`` records to the provider chosen by their company."""

from collections import defaultdict

from odoo import api
from odoo import fields
from odoo import models


class SmsSms(models.Model):
    _inherit = "sms.sms"

    record_company_id = fields.Many2one("res.company", string="Société", ondelete="set null")
    sms_voipms_message_ids = fields.Char(string="Identifiants VoIP.ms", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        """Default the company so the provider can be resolved later."""
        for vals in vals_list:
            vals.setdefault("record_company_id", self.env.company.id)
        return super().create(vals_list)

    def _get_sms_company(self):
        return (
            self.mail_message_id.record_company_id
            or self.record_company_id
            or super()._get_sms_company()
        )

    def send(self, unlink_sent=True, raise_exception=False):
        """Refuse early when the company cannot send through VoIP.ms.

        The composer calls ``send()`` directly: raising here reaches the user.
        The cron calls ``_send()`` instead, so it is not broken by a
        misconfiguration (``_send_sms_batch`` marks the SMS in error).
        """
        if not self:
            return super().send(unlink_sent=unlink_sent, raise_exception=raise_exception)
        outgoing = self.filtered(lambda sms: sms.state == "outgoing" and not sms.to_delete)
        if outgoing:
            for company in outgoing._get_sms_company().filtered(
                lambda company: company.sms_provider == "voipms"
            ):
                company._assert_sms_voipms_ready()
        return super().send(unlink_sent=unlink_sent, raise_exception=raise_exception)

    def _split_by_api(self):
        """Group SMS by company and route VoIP.ms companies to their API."""
        sms_by_company = defaultdict(lambda: self.env["sms.sms"])
        todo_via_super = self.browse()
        for sms in self:
            sms_by_company[sms._get_sms_company()] += sms
        for company, company_sms in sms_by_company.items():
            if company and company.sms_provider == "voipms":
                sms_api = company._get_sms_api_class()(self.env)
                sms_api._set_company(company)
                yield sms_api, company_sms
            else:
                todo_via_super += company_sms
        if todo_via_super:
            yield from super(SmsSms, todo_via_super)._split_by_api()

    def _get_send_batch_size(self):
        companies = self._get_sms_company()
        if companies and any(company.sms_provider == "voipms" for company in companies):
            return (
                self.env["ir.config_parameter"].sudo().get_int("sms_voipms.session.batch.size")
                or 10
            )
        return super()._get_send_batch_size()

    def _handle_call_result_hook(self, results):
        """Keep the VoIP.ms message ids on the tracker (SMS get deleted)."""
        voipms_sms = self.filtered(lambda sms: sms._get_sms_company().sms_provider == "voipms")
        sms_by_uuid = voipms_sms.grouped("uuid")
        for result in results:
            sms = sms_by_uuid.get(result.get("uuid"))
            message_ids = result.get("sms_voipms_message_ids")
            if sms and message_ids:
                sms.sms_voipms_message_ids = message_ids
                if sms.sms_tracker_id:
                    sms.sms_tracker_id.sms_voipms_message_ids = message_ids
        return super(SmsSms, self - voipms_sms)._handle_call_result_hook(results)
