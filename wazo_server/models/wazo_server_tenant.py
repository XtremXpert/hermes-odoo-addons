# Part of the wazo_server Odoo module. See LICENSE for details.
"""Tenants Wazo vus depuis le serveur.

Créer un tenant n'est pas un appel, c'est une **séquence** : le tenant, puis
son contexte et ses plages, puis son administrateur, ses droits et son jeton.
Un tenant neuf n'a **ni contexte ni utilisateur** — sans la deuxième étape il
est inutilisable, `wazo_phone` n'ayant nulle part où créer un poste.

La création vit dans **wazo-auth** (``POST /api/auth/0.1/tenants``). Le plugin
``tenant`` de wazo-confd est en **lecture seule** : c'est seulement lui qui dit
si les templates SIP ont été générés (``sip_templates_generated``), champ que
wazo-auth ne rend pas.

Ce que ce module **ne fait pas** : cloisonner les tenants. Mesuré sur un
serveur réel, un jeton de tenant peut lire les données d'un autre tenant en
changeant l'en-tête ``Wazo-Tenant`` : les ACL de Wazo sont des chaînes
indépendantes du tenant. La frontière se place à l'URL, voir
``doc/P5_WAZO_SERVER_SPEC.md``.
"""

import re
import secrets
import string
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.wazo_phone.services.wazo_client import (
    WazoAPIError,
    WazoClient,
)


class WazoServerTenant(models.Model):
    _name = 'wazo.server.tenant'
    _description = 'Tenant Wazo'
    _rec_name = 'name'
    _order = 'name'

    #: Wazo impose son propre motif au **slug d'un tenant** : lettres non
    #: accentuées, chiffres et souligné, dix caractères au plus. C'est plus
    #: strict que le slug générique de Wazo (`-` autorisé, 80 caractères) :
    #: un refus local vaut mieux qu'un 400 au milieu de la séquence.
    _WAZO_SLUG_RE = re.compile(r'^[a-zA-Z0-9_]+$')
    _WAZO_SLUG_MAX = 10

    #: Politique qui porte les droits d'administration côté Wazo (14 ACL,
    #: dont `confd.#`). Elle est créée par Wazo dans le tenant maître.
    _POLITIQUE_ADMIN = 'wazo_default_admin_policy'

    #: Durée de vie du jeton fabriqué pour le tenant : dix ans, le maximum
    #: accepté par wazo-auth (315360000 secondes). Un jeton d'intégration n'a
    #: pas à expirer au bout d'une heure comme une session de navigateur.
    _TOKEN_EXPIRATION = 315360000

    name = fields.Char(
        string='Nom du tenant', required=True,
        help="Nom lisible du tenant. Sert aussi, une fois nettoyé, à proposer "
             "un slug.")
    slug = fields.Char(
        string='Identifiant', required=True,
        help="Lettres non accentuées, chiffres et « _ » uniquement, "
             "10 caractères au maximum : contrainte de Wazo.")
    parent_id = fields.Many2one(
        'wazo.server.tenant', string='Tenant parent', ondelete='restrict',
        help="Laisser vide pour rattacher le tenant à la racine du serveur, "
             "qui est découverte automatiquement.")
    remote_uuid = fields.Char(
        string='UUID Wazo', readonly=True, copy=False,
        help="Identifiant du tenant côté Wazo. Consigné dès sa création : "
             "c'est lui qui permet de reprendre ou de supprimer.")
    state = fields.Selection(
        selection=[
            ('new', 'À créer'),
            ('created', 'Créé'),
            ('error', 'Erreur'),
        ],
        string='État', default='new', required=True, copy=False)

    context_name = fields.Char(
        string='Contexte', compute='_compute_context_name', store=True,
        help="Étiquette du contexte interne demandée à Wazo : "
             "« ctx-<identifiant>-internal ».")
    remote_context_name = fields.Char(
        string='Contexte (nom Wazo)', readonly=True, copy=False,
        help="Nom du contexte tel que Wazo l'a créé — il y ajoute un suffixe. "
             "C'est cette valeur qu'il faut donner à wazo_phone.")
    context_id = fields.Integer(
        string='ID du contexte', readonly=True, copy=False)
    user_range_start = fields.Char(string='Postes — début', default='1000')
    user_range_end = fields.Char(string='Postes — fin', default='1999')
    group_range_start = fields.Char(string='Groupes — début', default='2000')
    group_range_end = fields.Char(string='Groupes — fin', default='2099')

    admin_username = fields.Char(
        string='Administrateur du tenant', default='odoo_admin')
    admin_user_uuid = fields.Char(string='UUID administrateur', readonly=True,
                                  copy=False)
    admin_password = fields.Char(
        string='Mot de passe administrateur', copy=False,
        groups='wazo_phone.group_wazo_manager',
        help="Généré à la création. À remettre au tenant avec le jeton.")
    api_token = fields.Char(
        string="Jeton d'API du tenant", copy=False,
        groups='wazo_phone.group_wazo_manager',
        help="Jeton fabriqué pour le tenant, à installer dans les réglages de "
             "son Odoo. Visible des gestionnaires seulement.")
    token_expires_at = fields.Datetime(
        string='Expiration du jeton', readonly=True, copy=False)
    error_message = fields.Text(string="Dernier message d'erreur", copy=False)
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------------
    # Contrôles locaux
    # ------------------------------------------------------------------

    @api.depends('slug')
    def _compute_context_name(self):
        for tenant in self:
            tenant.context_name = (
                'ctx-%s-internal' % tenant.slug if tenant.slug else False)

    @api.constrains('slug')
    def _check_slug_is_a_wazo_tenant_slug(self):
        """Le slug doit passer le motif de Wazo **avant** tout appel."""
        for tenant in self:
            slug = tenant.slug or ''
            if not slug:
                continue  # requis : le cas vide ne vient pas d'ici
            if len(slug) > self._WAZO_SLUG_MAX:
                raise ValidationError(
                    "L'identifiant d'un tenant est limité à %d caractères par "
                    'Wazo (ici %d) : « %s ».'
                    % (self._WAZO_SLUG_MAX, len(slug), slug))
            if not self._WAZO_SLUG_RE.match(slug):
                raise ValidationError(
                    "L'identifiant d'un tenant ne peut contenir que des "
                    'lettres non accentuées, des chiffres et « _ » : ni accent, '
                    'ni tiret, ni espace. Identifiant refusé : « %s ».' % slug)

    # ------------------------------------------------------------------
    # Client Wazo
    # ------------------------------------------------------------------

    def _client(self, tenant_uuid=None):
        """Client pointant sur le tenant visé (le tenant maître par défaut).

        Les appels confd d'un tenant neuf doivent porter **son** en-tête : le
        créer dans le maître reviendrait à configurer le mauvais client.
        """
        return WazoClient(self.env, tenant_id=tenant_uuid or None)

    def _racine(self, client):
        """UUID du tenant racine, découvert par l'API.

        Un tenant racine est son propre parent : c'est le seul repère sûr, le
        champ « parent » n'existant pas côté API. Sans lui, un tenant créé
        flotterait hors de l'arborescence.
        """
        reponse = client.auth('GET', '/tenants') or {}
        for item in reponse.get('items') or []:
            if item.get('uuid') and item.get('uuid') == item.get('parent_uuid'):
                return item['uuid']
        return None

    @staticmethod
    def _mot_de_passe():
        """Mot de passe d'administration : alphanumérique, donc sans surprise.

        Ni accent, ni symbole : il traverse une API et sera recopié à la main
        par le tenant. Il n'est pas tiré d'un dictionnaire non plus.
        """
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(24))

    @staticmethod
    def _vers_datetime(horodatage):
        """Date ISO de Wazo vers date Odoo (naïve, en temps universel)."""
        if not horodatage:
            return False
        try:
            return datetime.strptime(str(horodatage)[:19], '%Y-%m-%dT%H:%M:%S')
        except (TypeError, ValueError):
            return False

    # ------------------------------------------------------------------
    # Création
    # ------------------------------------------------------------------

    def action_create_on_wazo(self):
        """Crée le tenant de bout en bout : tenant, contexte, accès, jeton.

        Chaque identifiant reçu est **consigné aussitôt**. Si la séquence
        s'interrompt, l'enregistrement passe en erreur **sans lever** : un
        ``UserError`` remonterait la transaction et effacerait la trace du
        tenant déjà créé sur Wazo. On garde au contraire de quoi reprendre ou
        supprimer proprement ce qui existe.
        """
        self.ensure_one()
        if self.state == 'created':
            raise UserError(
                "Le tenant « %s » existe déjà sur Wazo. Pour le reprendre, "
                'supprimez-le d\'abord ou créez-en un autre.' % self.name)
        client = self._client()
        # Un tenant déjà connu (reprise) se relit ; un tenant créé à l'instant
        # n'a rien à relire — et ne doit surtout pas être recréé.
        nouveau = not self.remote_uuid
        try:
            # 1. Le tenant, rattaché à la racine ou au parent déclaré. Il n'est
            #    créé qu'une fois : le recréer après un échec ferait un doublon
            #    sur le PBX, avec deux tenants du même nom.
            if not self.remote_uuid:
                corps = {'name': self.name, 'slug': self.slug}
                parent = self.parent_id.remote_uuid or self._racine(client)
                if parent:
                    corps['parent_uuid'] = parent
                reponse = client.auth('POST', '/tenants', body=corps) or {}
                self.remote_uuid = reponse.get('uuid')
                if not self.remote_uuid:
                    raise WazoAPIError(
                        "Wazo n'a pas rendu l'identifiant du tenant créé.")
            client_tenant = self._client(self.remote_uuid)

            # 2. Le contexte et ses plages, dans le tenant. Repris s'il existe
            #    déjà — la réponse d'un premier appel a pu se perdre —, créé
            #    sinon. Les bornes sont transmises en texte, comme Wazo les rend.
            contexte = None
            if self.context_id:
                contexte = {'id': self.context_id,
                            'name': self.remote_context_name}
            elif not nouveau:
                contexte = self._contexte_existant(client_tenant)
            if not contexte:
                contexte = client_tenant.conf('POST', '/contexts', body={
                    'label': self.context_name,
                    'user_ranges': [{'start': self.user_range_start,
                                     'end': self.user_range_end}],
                    'group_ranges': [{'start': self.group_range_start,
                                      'end': self.group_range_end}],
                }) or {}
            self.context_id = contexte.get('id') or 0
            self.remote_context_name = contexte.get('name') or self.context_name

            # 3. L'administrateur du tenant : créé **dans** le tenant (paramètre
            #    et en-tête), puis doté de la politique d'administration.
            # C'est l'en-tête du tenant qui fait foi : wazo-auth **ignore** le
            # paramètre `tenant_uuid` passé en chaîne de requête (mesuré en
            # direct), et un utilisateur créé sans en-tête naîtrait dans le
            # maître — le tenant se retrouverait sans administrateur.
            if not self.admin_user_uuid:
                utilisateur = (None if nouveau else
                               self._administrateur_existant(client_tenant))
                if utilisateur:
                    self.admin_user_uuid = utilisateur.get('uuid')
                else:
                    mot_de_passe = self.admin_password or self._mot_de_passe()
                    utilisateur = client_tenant.auth(
                        'POST', '/users',
                        params={'tenant_uuid': self.remote_uuid},
                        body={'username': self.admin_username,
                              'password': mot_de_passe,
                              'firstname': 'Administrateur',
                              'lastname': self.name[:40]}) or {}
                    self.admin_user_uuid = utilisateur.get('uuid')
                    self.admin_password = mot_de_passe
                if not self.admin_user_uuid:
                    raise WazoAPIError(
                        "Wazo n'a pas rendu l'identifiant de l'administrateur "
                        'créé.')
            if not self.admin_password:
                # Un administrateur repris sans son mot de passe ne peut pas
                # recevoir de jeton : wazo-auth ne le rend à personne. Mieux
                # vaut le dire que de laisser un tenant sans accès.
                raise WazoAPIError(
                    "L'administrateur « %s » existe déjà sur Wazo mais son mot "
                    'de passe est inconnu de cette base : supprimez le tenant '
                    "sur Wazo, puis relancez la création." % self.admin_username)
            politique = self._politique_admin(client)
            if politique:
                client_tenant.auth('PUT', '/users/%s/policies/%s'
                                   % (self.admin_user_uuid, politique))

            # 4. Son jeton, en Basic : les identifiants, pas le jeton du maître.
            donnees = client.token(self.admin_username, self.admin_password,
                                   expiration=self._TOKEN_EXPIRATION)
            self.api_token = donnees.get('token')
            self.token_expires_at = self._vers_datetime(
                donnees.get('expires_at'))
            self.state = 'created'
            self.error_message = False
            return True
        except WazoAPIError as erreur:
            self.state = 'error'
            self.error_message = str(erreur)
            return False

    def _contexte_existant(self, client_tenant):
        """Le contexte du tenant, s'il a déjà été créé (reprise).

        Un ``POST`` dont la réponse s'est perdue laisse un contexte sans trace
        locale : le recréer produirait un doublon invisible depuis Odoo. On
        relit donc la liste du tenant et on reconnaît le contexte à son
        étiquette — la seule que nous ayons posée.
        """
        reponse = client_tenant.conf('GET', '/contexts') or {}
        for item in reponse.get('items') or []:
            if item.get('label') == self.context_name:
                return item
        return None

    def _administrateur_existant(self, client_tenant):
        """L'administrateur du tenant, s'il a déjà été créé (reprise)."""
        reponse = client_tenant.auth('GET', '/users') or {}
        for item in reponse.get('items') or []:
            if item.get('username') == self.admin_username:
                return item
        return None

    def _politique_admin(self, client):
        """UUID de la politique d'administration, résolu depuis son slug.

        L'association attend un UUID, le slug est stable et lisible : c'est le
        slug qui est retenu ici, résolu à chaque création.
        """
        reponse = client.auth('GET', '/policies') or {}
        for item in reponse.get('items') or []:
            if item.get('slug') == self._POLITIQUE_ADMIN:
                return item.get('uuid')
        return None

    # ------------------------------------------------------------------
    # Suppression
    # ------------------------------------------------------------------

    def action_delete_on_wazo(self):
        """Supprime le tenant — après avoir vérifié qu'il ne porte plus rien.

        Trois appels, dans cet ordre : le contexte **du** tenant, son
        administrateur, puis le tenant. Supprimer le tenant d'abord rendrait
        son contexte inaccessible et laisserait un orphelin sur le PBX ; c'est
        la leçon des groupes d'appel (P4.3), où un échec en milieu de séquence
        avait laissé une trace sans propriétaire.
        """
        self.ensure_one()
        if self.state != 'created' or not self.remote_uuid:
            raise UserError(
                "Le tenant « %s » n'existe pas sur Wazo : il n'y a rien à "
                'supprimer.' % self.name)
        client_tenant = self._client(self.remote_uuid)
        postes = (client_tenant.conf('GET', '/users') or {}).get('total') or 0
        lignes = (client_tenant.conf('GET', '/lines') or {}).get('total') or 0
        if postes or lignes:
            raise UserError(
                "Le tenant « %s » porte encore %d poste(s) et %d ligne(s) : "
                'supprimez-les depuis l\'instance Odoo du tenant avant de '
                'supprimer son tenant.' % (self.name, postes, lignes))
        if self.context_id:
            client_tenant.conf('DELETE', '/contexts/%s' % self.context_id)
        if self.admin_user_uuid:
            self._client().auth('DELETE', '/users/%s' % self.admin_user_uuid)
        self._client().auth('DELETE', '/tenants/%s' % self.remote_uuid)
        self.write({
            'state': 'new',
            'remote_uuid': False,
            'context_id': 0,
            'remote_context_name': False,
            'admin_user_uuid': False,
            'admin_password': False,
            'api_token': False,
            'token_expires_at': False,
            'error_message': False,
        })
        return True
