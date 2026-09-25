# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Groupes d'appel Wazo (ring groups).

Un groupe d'appel est un poste qui sonne chez plusieurs utilisateurs. Sa
création côté Wazo demande **trois appels**, dans cet ordre :

1. ``POST /groups`` — le groupe (``label``, stratégie de sonnerie, délais) ;
2. ``POST /extensions`` — son extension, qui doit **exister avant** d'être
   associée ;
3. ``PUT /groups/{uuid}/extensions/{extension_id}`` — l'association.

Puis, s'il y a des membres, ``PUT /groups/{uuid}/members/users`` : cet appel
**remplace l'ensemble** des membres et les désigne par **uuid** d'utilisateur.
Un membre doit donc avoir été synchronisé au préalable, sans quoi son uuid
n'existe pas côté Wazo (``remote_user_uuid``).

Le poste du groupe est pris dans la plage ``group`` du contexte — 2000-2099 sur
le PBX de référence —, jamais dans celle des utilisateurs : le contrôle des
plages est celui du mixin :class:`~odoo.addons.wazo_phone.models.
wazo_extension_mixin.WazoExtensionMixin`, ici avec ``_extension_type = 'group'``.
"""

import re

from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

from odoo import api
from odoo import fields
from odoo import models

from ..services.wazo_client import WazoAPIError


class WazoRingGroup(models.Model):
    _name = 'wazo.ring.group'
    _inherit = ['wazo.extension.mixin']
    _extension_type = 'group'
    _description = "Groupe d'appel Wazo"
    _rec_name = 'name'

    #: Wazo valide le libellé d'un groupe par un motif (``LABEL_REGEX`` de son
    #: schéma), longueur 128 comprise. Ce libellé finit dans ``queues.conf``
    #: d'Asterisk, d'où l'exclusion des accents et de la ponctuation riche : un
    #: refus local vaut mieux qu'un 400 de l'API au milieu d'une synchro.
    _WAZO_LABEL_RE = re.compile(r'^[-_.a-zA-Z0-9 ]+$')
    _WAZO_LABEL_MAX = 128

    name = fields.Char(
        string='Nom', required=True,
        help="Nom du groupe côté Wazo : lettres non accentuées, chiffres, "
             "espaces et « - _ . » uniquement. C'est une contrainte de Wazo, "
             "qui reprend ce libellé dans la configuration d'Asterisk.")
    ring_strategy = fields.Selection(
        selection=[
            ('all', 'Tous en même temps'),
            ('linear', "Un après l'autre, par priorité"),
            ('random', 'Au hasard'),
            ('least_recent', 'Celui qui a traité le moins récemment'),
            ('fewest_calls', "Celui qui a le moins d'appels traités"),
            ('memorized_round_robin', 'Rotation mémorisée'),
            ('weight_random', 'Au hasard pondéré'),
        ],
        string='Stratégie de sonnerie', default='all', required=True)
    user_timeout = fields.Integer(
        string='Sonnerie par membre (s)', default=15,
        help='Nombre de secondes pendant lesquelles chaque membre sonne.')
    retry_delay = fields.Integer(
        string='Délai avant reprise (s)', default=5,
        help='Nombre de secondes avant de faire ressonner un membre.')
    timeout = fields.Integer(
        string='Durée totale (s)',
        help='Durée maximale de sonnerie avant renvoi. Laisser à 0 pour '
             'sonner indéfiniment.')
    member_ids = fields.One2many(
        'wazo.ring.group.member', 'group_id', string='Membres',
        help="Utilisateurs qui sonnent, dans l'ordre de leur priorité. Chacun "
             "doit être synchronisé sur Wazo avant de pouvoir être rattaché.")
    wazo_state = fields.Selection(
        selection=[
            ('new', 'Nouveau'),
            ('synced', 'Synchronisé'),
            ('error', 'Erreur'),
        ],
        string='État', default='new', required=True)
    remote_group_id = fields.Char(
        string='UUID groupe Wazo',
        help="UUID du groupe côté Wazo — c'est lui qui sert aux associations "
             "(extension, membres).")
    remote_extension_id = fields.Integer(string='ID poste Wazo')
    error_message = fields.Text(string="Dernier message d'erreur")
    active = fields.Boolean(default=True)
    member_count = fields.Integer(
        string='Membres', compute='_compute_member_count')

    @api.depends('member_ids')
    def _compute_member_count(self):
        for groupe in self:
            groupe.member_count = len(groupe.member_ids)

    # ------------------------------------------------------------------
    # Contrôle local du libellé
    # ------------------------------------------------------------------

    @api.constrains('name')
    def _check_name_is_a_wazo_label(self):
        """Le libellé doit passer le motif de Wazo **avant** tout appel.

        Sans ce contrôle, un nom accentué ou ponctué n'échoue qu'au
        ``POST /groups``, une fois la synchronisation engagée.
        """
        for groupe in self:
            nom = groupe.name or ''
            if not nom:
                continue  # requis : le cas vide ne vient pas d'ici
            if len(nom) > self._WAZO_LABEL_MAX:
                raise ValidationError(
                    'Le nom du groupe est limité à %d caractères par Wazo '
                    '(ici %d).' % (self._WAZO_LABEL_MAX, len(nom)))
            if not self._WAZO_LABEL_RE.match(nom):
                raise ValidationError(
                    'Le nom du groupe ne peut contenir que des lettres non '
                    'accentuées, des chiffres, des espaces et les caractères '
                    '« - _ . » : Wazo le reprend dans la configuration '
                    "d'Asterisk. Nom refusé : « %s »." % nom)

    # ------------------------------------------------------------------
    # Synchronisation vers Wazo
    # ------------------------------------------------------------------

    def _group_body(self):
        """Corps de ``POST /groups``.

        ``name`` est en **lecture seule** côté API (Wazo le génère) : le nom
        convivial passe par ``label``. Les délais à 0 ne sont pas envoyés —
        pour ``timeout``, l'absence signifie « sonner indéfiniment ».
        """
        corps = {
            'label': self.name,
            'ring_strategy': self.ring_strategy,
        }
        if self.user_timeout:
            corps['user_timeout'] = self.user_timeout
        if self.retry_delay:
            corps['retry_delay'] = self.retry_delay
        if self.timeout:
            corps['timeout'] = self.timeout
        return corps

    def _members_payload(self):
        """Corps de ``PUT /groups/{uuid}/members/users``.

        Les membres se désignent par **uuid** d'utilisateur. L'appel remplace
        l'ensemble : la liste envoyée est donc toujours complète, et **ordonnée
        par priorité** — c'est cet ordre que Wazo suit pour la stratégie « un
        après l'autre », la plus petite priorité sonnant en premier.
        """
        return {'users': [
            {'uuid': membre.user_id.remote_user_uuid,
             'priority': membre.priority}
            for membre in self.member_ids.sorted('priority')]}

    def action_sync_wazo(self):
        """Crée (ou reprend) le groupe d'appel et son poste sur Wazo."""
        self.ensure_one()
        if self.wazo_state == 'synced':
            raise UserError(
                "Le groupe d'appel %s est déjà synchronisé sur Wazo."
                % self.name)
        if not self.extension:
            raise UserError(
                'Le poste du groupe est requis avant de synchroniser sur Wazo.')
        client = self._wazo_client()
        context = self._wazo_line_context()
        # Chaque membre doit avoir son uuid Wazo. Un utilisateur synchronisé
        # avant l'arrivée du champ (P4.3) n'en a pas : on le relit plutôt que de
        # refuser, sinon la fonctionnalité resterait fermée à tout l'existant.
        membres = self.member_ids
        sans_uuid = self.env['wazo.user']
        for membre in membres:
            if not membre.user_id._ensure_remote_user_uuid(client):
                sans_uuid |= membre.user_id
        if sans_uuid:
            raise UserError(
                "Ces utilisateurs n'ont pas d'uuid côté Wazo, sans lequel ils "
                "ne peuvent pas être membres du groupe : %s. Synchronisez-les "
                "d'abord, ou vérifiez leur synchronisation."
                % ', '.join(sans_uuid.mapped('name')))
        try:
            extension = self._find_wazo_extension(client)
            # Contrôle du poste (plage, type, disponibilité, reprise) : refus
            # AVANT toute écriture distante.
            self._check_extension_allowed(client, context, extension)
            if extension is None:
                # 1. Le groupe d'abord : il porte le label et la stratégie.
                groupe = client.conf(
                    'POST', '/groups', body=self._group_body())
                # L'uuid est consigné **tout de suite**. Si la suite échoue, la
                # ressource déjà créée reste connue — donc supprimable et
                # reprenable. Sinon elle vivrait au PBX sans trace dans Odoo.
                self.sudo().write({'remote_group_id': groupe.get('uuid')})
                # 2. L'extension ensuite : elle doit exister avant d'être
                #    associée.
                extension = client.conf('POST', '/extensions', body={
                    'exten': self.extension, 'context': context})
                self.sudo().write({
                    'remote_extension_id': extension.get('id')})
                # 3. L'association.
                client.conf('PUT', '/groups/%s/extensions/%s'
                            % (groupe['uuid'], extension['id']))
            else:
                # Reprise après échec : l'extension porte la relation vers son
                # groupe, quand l'association a déjà eu lieu.
                groupe = extension.get('group') or {}
                if not groupe.get('uuid'):
                    # Extension créée mais association manquante : on crée le
                    # groupe et on la rattache.
                    groupe = client.conf(
                        'POST', '/groups', body=self._group_body())
                    # Consigné tout de suite, pour la même raison qu'à la
                    # création neuve.
                    self.sudo().write(
                        {'remote_group_id': groupe.get('uuid')})
                    client.conf('PUT', '/groups/%s/extensions/%s'
                                % (groupe['uuid'], extension['id']))
            if membres:
                client.conf(
                    'PUT', '/groups/%s/members/users' % groupe['uuid'],
                    body=self._members_payload())
        except UserError:
            # Un refus de validation s'adresse à l'utilisateur : il remonte tel
            # quel plutôt que d'être transformé en état d'erreur silencieux.
            raise
        except WazoAPIError as error:
            self.write({
                'wazo_state': 'error',
                'error_message': str(error),
            })
            return False
        self.sudo().write({
            'wazo_state': 'synced',
            'remote_group_id': groupe.get('uuid'),
            'remote_extension_id': extension.get('id'),
            'error_message': False,
        })
        return True

    def action_retry_sync(self):
        """Reprise après échec : même flux, l'état ``error`` l'autorisant."""
        return self.action_sync_wazo()

    def action_delete_wazo(self):
        """Supprime le groupe et son poste côté Wazo (idempotent)."""
        self.ensure_one()
        client = self._wazo_client()

        def _ignore_404(method, path):
            try:
                client.conf(method, path)
            except WazoAPIError as error:
                if 'HTTP 404' not in str(error):
                    raise
            return True

        try:
            # Le groupe d'abord : sa suppression libère l'association, ensuite
            # l'extension est supprimée proprement.
            if self.remote_group_id:
                _ignore_404('DELETE', '/groups/%s' % self.remote_group_id)
            if self.remote_extension_id:
                _ignore_404(
                    'DELETE', '/extensions/%s' % self.remote_extension_id)
        except WazoAPIError as error:
            self.write({
                'wazo_state': 'error',
                'error_message': str(error),
            })
            return False
        self.sudo().write({
            'wazo_state': 'new',
            'remote_group_id': False,
            'remote_extension_id': False,
            'error_message': False,
        })
        return True


class WazoRingGroupMember(models.Model):
    """Membre d'un groupe d'appel.

    Le lien groupe ↔ utilisateur n'est pas une simple relation : il porte la
    **priorité** de sonnerie, celle que Wazo lit pour la stratégie « un après
    l'autre ». D'où un modèle plutôt qu'un ``Many2many`` : un lien implicite ne
    saurait pas la porter.
    """

    _name = 'wazo.ring.group.member'
    _description = "Membre d'un groupe d'appel Wazo"
    _order = 'priority, id'

    group_id = fields.Many2one(
        'wazo.ring.group', string='Groupe', required=True,
        ondelete='cascade')
    user_id = fields.Many2one(
        'wazo.user', string='Utilisateur', required=True,
        ondelete='cascade')
    priority = fields.Integer(
        string='Priorité', default=10,
        help="Ordre de sonnerie : la plus petite priorité sonne d'abord. Seul "
             "l'ordre compte, les écarts ne veulent rien dire — d'où des pas "
             "de 10, qui laissent de la place pour insérer.")
    extension = fields.Char(
        related='user_id.extension', string='Poste', readonly=True)
    wazo_state = fields.Selection(
        related='user_id.wazo_state', string='État', readonly=True)

    @api.constrains('group_id', 'user_id')
    def _check_member_is_unique(self):
        """Un même utilisateur ne sonne qu'une fois dans le même groupe."""
        for membre in self:
            if not (membre.group_id and membre.user_id):
                continue
            doublon = self.search([
                ('id', '!=', membre.id),
                ('group_id', '=', membre.group_id.id),
                ('user_id', '=', membre.user_id.id)], limit=1)
            if doublon:
                raise ValidationError(
                    "%s est déjà membre de ce groupe d'appel."
                    % membre.user_id.display_name)
