# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Journal d'appels Wazo synchronisé depuis wazo-call-logd."""

import logging
import re
from datetime import datetime, timedelta, timezone

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.wazo_client import WazoAPIError, WazoClient

_logger = logging.getLogger(__name__)

PER_PAGE = 200
MAX_PAGES = 50


def _parse_wazo_datetime(value):
    """Convertit un instant ISO-8601 de Wazo en datetime naive UTC."""
    if not value:
        return False
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return False
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


class WazoCdr(models.Model):
    _name = 'wazo.cdr'
    _description = "Journal d'appel Wazo"
    _order = 'date_start desc'

    _wazo_cdr_uniq = models.Constraint(
        'unique(wazo_cdr_id)',
        'Un enregistrement de journal d\'appel Wazo n\'existe qu\'une fois.')

    wazo_cdr_id = fields.Integer(
        string='ID Wazo', required=True, index=True, readonly=True)
    date_start = fields.Datetime(string='Début', index=True, readonly=True)
    date_end = fields.Datetime(string='Fin', readonly=True)
    answered = fields.Boolean(string='Répondu', readonly=True)
    duration = fields.Integer(string='Durée (s)', readonly=True)
    caller_num = fields.Char(string='Numéro appelant', readonly=True)
    caller_name = fields.Char(string='Nom appelant', readonly=True)
    destination_num = fields.Char(string='Destination', readonly=True)
    destination_name = fields.Char(string='Nom destination', readonly=True)
    call_direction = fields.Selection(
        selection=[
            ('outbound', 'Sortant'),
            ('inbound', 'Entrant'),
            ('internal', 'Interne'),
        ],
        string='Sens', readonly=True)
    partner_id = fields.Many2one(
        'res.partner', string='Contact', ondelete='set null', index=True,
        help='Contact Odoo identifié à partir des numéros de l\'appel.')

    # ------------------------------------------------------------------
    # Synchronisation
    # ------------------------------------------------------------------

    @api.model
    def _upsert_cdr(self, item, partner_cache):
        """Crée ou met à jour un CDR ; retourne le nombre de créations."""
        cdr_id = item.get('id')
        if cdr_id is None:
            return 0
        # call-logd v1.0 : le campagnard est ``source_extension``/
        # ``source_name`` ; ``destination_extension``/``destination_name``.
        source_num = str(item.get('source_extension') or '')
        destination_num = str(item.get('destination_extension') or '')
        partner_id = (self.env['wazo.cdr']
                      ._find_partner_for_cdr(source_num, destination_num,
                                             partner_cache)
                      .id)
        vals = {
            'date_start': _parse_wazo_datetime(item.get('start')),
            'date_end': _parse_wazo_datetime(item.get('end')),
            'answered': bool(item.get('answered')),
            'duration': int(item.get('duration') or 0),
            # call-logd v1.0 : nommage ``source_*`` (et non ``caller_id_*``).
            'caller_num': source_num,
            'caller_name': str(item.get('source_name') or ''),
            'destination_num': destination_num,
            'destination_name': str(item.get('destination_name') or ''),
            'call_direction': item.get('call_direction') or False,
            'partner_id': partner_id or False,
        }
        record = self.search([('wazo_cdr_id', '=', cdr_id)], limit=1)
        if record:
            record.write(vals)
            return 0
        self.create(dict(vals, wazo_cdr_id=cdr_id))
        return 1

    def _search_partner_by_phone_digits(self, digits):
        """Trouve un contact dont le téléphone contient ``digits``.

        Le numéro stocké côté contact peut être formaté (indicatif,
        espaces, tirets, points, parenthèses) ; le matching ignore donc les
        séparateurs non chiffrés. Limité aux numéros plausibles (>= 7
        chiffres) pour éviter les faux positifs sur les postes courts.
        """
        if not digits or len(digits) < 7:
            return self.env['res.partner']
        # Chaque chiffre peut être suivi d'au plus un caractère non chiffré.
        pattern = '[^0-9]?'.join(digits)
        self.env.cr.execute(
            "SELECT id FROM res_partner "
            "WHERE phone IS NOT NULL AND phone <> '' AND phone ~ %s "
            "LIMIT 1", (pattern,))
        row = self.env.cr.fetchone()
        return (self.env['res.partner'].browse(row[0])
                if row else self.env['res.partner'])

    @api.model
    def _find_partner_for_cdr(self, caller_num, destination_num, cache):
        """Identifie le contact Odoo d'un appel.

        Matching volontairement restreint (v1) : d'abord le poste Wazo du
        contact (numéros courts, matching spécifique), puis son numéro de
        téléphone (tolérant aux séparateurs de formatage).
        """
        for number in (destination_num, caller_num):
            digits = re.sub(r'\D', '', number)
            if not digits:
                continue
            key = ('match', digits)
            if key in cache:
                partner = cache[key]
                if partner:
                    return partner
                continue
            # Poste Wazo (extension) d'abord : cas des numéros courts.
            partner = self.env['res.partner'].search(
                [('wazo_user_id.extension', '=', digits)], limit=1)
            # Puis le téléphone du contact (numéros longs, formatés).
            if not partner:
                partner = self._search_partner_by_phone_digits(digits)
            cache[key] = partner
            if partner:
                return partner
        return self.env['res.partner']

    @api.model
    def sync_cdrs(self, since=None, until=None, limit_days=1):
        """Synchronise le journal d'appels Wazo vers la base locale.

        ``since``/``until`` : datetimes (naive, UTC). Par défaut : les
        ``limit_days`` derniers jours. Retourne le nombre de CDR créés.
        """
        client = WazoClient(self.env)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        until = until or now
        since = since or (until - timedelta(days=limit_days))
        created = 0
        seen = 0
        partner_cache = {}
        for page in range(1, MAX_PAGES + 1):
            result = client.call_logd('GET', '/cdr', params={
                'start': since.strftime('%Y-%m-%dT%H:%M:%S+00:00'),
                'end': until.strftime('%Y-%m-%dT%H:%M:%S+00:00'),
                'page': page,
                'per_page': PER_PAGE,
            })
            items = (result or {}).get('items') or []
            for item in items:
                created += self._upsert_cdr(item, partner_cache)
            seen += len(items)
            total = (result or {}).get('total')
            if not items or (total is not None and seen >= total):
                break
        return created

    def cron_sync_cdrs(self):
        """Tâche planifiée : synchronise les 24 dernières heures."""
        try:
            self.sync_cdrs()
        except WazoAPIError as error:
            _logger.warning('Synchronisation Wazo CDR échouée : %s', error)

    @api.model
    def action_sync_cdrs(self, days=1):
        """Synchronisation manuelle (bouton du formulaire)."""
        try:
            self.sync_cdrs(limit_days=days)
        except WazoAPIError as error:
            raise UserError(str(error)) from error
        return {
            'type': 'ir.actions.act_window',
            'name': "Journal d'appels",
            'res_model': 'wazo.cdr',
            'view_mode': 'list',
            'domain': [('date_start', '>=',
                        fields.Datetime.now() - timedelta(days=days))],
        }

    def action_open_cdrs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Journal d'appels",
            'res_model': 'wazo.cdr',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
        }

    @api.model
    def action_open_partner_cdrs(self, partner):
        """Journal d'appels d'un contact donné (bouton du formulaire)."""
        partner = partner.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Journal d'appels de %s" % partner.name,
            'res_model': 'wazo.cdr',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', partner.id)],
        }
