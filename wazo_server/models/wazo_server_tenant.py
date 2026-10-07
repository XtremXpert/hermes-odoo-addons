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

import logging
import re
import secrets
import string
from datetime import datetime

_logger = logging.getLogger(__name__)

from odoo import api
from odoo import fields
from odoo import models
from odoo.addons.wazo_phone.services.wazo_client import WazoAPIError
from odoo.addons.wazo_phone.services.wazo_client import WazoClient
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

#: Bloc remis à l'exploitant du tenant. Les libellés sont ceux des réglages de
#: `wazo_phone` (« Réglages → Téléphonie Wazo ») : la fiche se recopie sans
#: traduction à faire, et un champ mal rempli se voit tout de suite.
ENTETE_REMISE = """Coordonnées du tenant « %(nom)s »

Réglages → Téléphonie Wazo
    URL du serveur Wazo : %(url)s
    Token API Wazo      : %(jeton)s
    Tenant Wazo (UUID)  : %(tenant)s
    Contexte des lignes : %(contexte)s

Administrateur du tenant dans Wazo :
    %(admin)s / %(mot_de_passe)s

Jeton valable jusqu'au %(expiration)s. Il ne s'agit pas d'une session : le
jeton sert à l'intégration, et il disparaît avec le tenant."""


class WazoServerTenant(models.Model):
    _name = "wazo.server.tenant"
    _description = "Tenant Wazo"
    _rec_name = "name"
    _order = "name"

    #: Wazo impose son propre motif au **slug d'un tenant** : lettres non
    #: accentuées, chiffres et souligné, dix caractères au plus. C'est plus
    #: strict que le slug générique de Wazo (`-` autorisé, 80 caractères) :
    #: un refus local vaut mieux qu'un 400 au milieu de la séquence.
    _WAZO_SLUG_RE = re.compile(r"^[a-zA-Z0-9_]+$")
    _WAZO_SLUG_MAX = 10

    #: Politique qui porte les droits d'administration côté Wazo (14 ACL,
    #: dont `confd.#`). Elle est créée par Wazo dans le tenant maître.
    _POLITIQUE_ADMIN = "wazo_default_admin_policy"

    #: Durée de vie du jeton fabriqué pour le tenant : dix ans, le maximum
    #: accepté par wazo-auth (315360000 secondes). Un jeton d'intégration n'a
    #: pas à expirer au bout d'une heure comme une session de navigateur.
    _TOKEN_EXPIRATION = 315360000

    name = fields.Char(
        string="Nom du tenant",
        required=True,
        help="Nom lisible du tenant. Sert aussi, une fois nettoyé, à proposer un slug.",
    )
    slug = fields.Char(
        string="Identifiant",
        required=True,
        help="Lettres non accentuées, chiffres et « _ » uniquement, "
        "10 caractères au maximum : contrainte de Wazo.",
    )
    parent_id = fields.Many2one(
        "wazo.server.tenant",
        string="Tenant parent",
        ondelete="restrict",
        help="Laisser vide pour rattacher le tenant à la racine du serveur, "
        "qui est découverte automatiquement.",
    )
    remote_uuid = fields.Char(
        string="UUID Wazo",
        readonly=True,
        copy=False,
        help="Identifiant du tenant côté Wazo. Consigné dès sa création : "
        "c'est lui qui permet de reprendre ou de supprimer.",
    )
    state = fields.Selection(
        selection=[
            ("new", "À créer"),
            ("created", "Créé"),
            ("error", "Erreur"),
        ],
        string="État",
        default="new",
        required=True,
        copy=False,
    )

    context_name = fields.Char(
        string="Contexte",
        compute="_compute_context_name",
        store=True,
        help="Étiquette du contexte interne demandée à Wazo : « ctx-<identifiant>-internal ».",
    )
    remote_context_name = fields.Char(
        string="Contexte (nom Wazo)",
        readonly=True,
        copy=False,
        help="Nom du contexte tel que Wazo l'a créé — il y ajoute un suffixe. "
        "C'est cette valeur qu'il faut donner à wazo_phone.",
    )
    context_id = fields.Integer(string="ID du contexte", readonly=True, copy=False)
    user_range_start = fields.Char(string="Postes — début", default="1000")
    user_range_end = fields.Char(string="Postes — fin", default="1999")
    group_range_start = fields.Char(string="Groupes — début", default="2000")
    group_range_end = fields.Char(string="Groupes — fin", default="2099")

    admin_username = fields.Char(string="Administrateur du tenant", default="odoo_admin")
    admin_user_uuid = fields.Char(string="UUID administrateur", readonly=True, copy=False)
    admin_password = fields.Char(
        string="Mot de passe administrateur",
        copy=False,
        groups="wazo_phone.group_wazo_manager",
        help="Généré à la création. À remettre au tenant avec le jeton.",
    )
    api_token = fields.Char(
        string="Jeton d'API du tenant",
        copy=False,
        groups="wazo_phone.group_wazo_manager",
        help="Jeton fabriqué pour le tenant, à installer dans les réglages de "
        "son Odoo. Visible des gestionnaires seulement.",
    )
    token_expires_at = fields.Datetime(string="Expiration du jeton", readonly=True, copy=False)
    error_message = fields.Text(string="Dernier message d'erreur", copy=False)
    handover_text = fields.Text(
        string="Coordonnées à remettre au tenant",
        compute="_compute_handover_text",
        groups="wazo_phone.group_wazo_manager",
        help="Bloc à copier tel quel par l'exploitant du tenant : où se posent "
        "les valeurs dans ses réglages, et ce qu'elles valent. Réservé aux "
        "gestionnaires, puisqu'il porte le jeton et le mot de passe.",
    )
    active = fields.Boolean(default=True)

    #: Date du dernier renouvellement du jeton — donc l'âge du secret en cours.
    token_rotated_at = fields.Datetime(string="Jeton renouvelé le", readonly=True, copy=False)
    #: L'ancien jeton a-t-il bien été révoqué ? Faux = il reste valable.
    previous_token_revoked = fields.Boolean(
        string="Ancien jeton révoqué", readonly=True, copy=False
    )
    #: Ce qu'il faut dire quand la révocation a échoué (jamais le secret).
    token_revocation_note = fields.Char(string="Note de révocation", readonly=True, copy=False)

    @api.depends(
        "state",
        "name",
        "remote_uuid",
        "context_name",
        "remote_context_name",
        "admin_username",
        "admin_password",
        "api_token",
        "token_expires_at",
        "token_rotated_at",
    )
    def _compute_handover_text(self):
        """Le bloc à copier, recalculé à chaque lecture.

        Non stocké : l'URL du serveur est relue à la demande, donc la fiche
        reste juste même si les réglages changent après coup.
        """
        url = self.env["ir.config_parameter"].sudo().get_str("wazo.url")
        for tenant in self:
            if tenant.state != "created" or not tenant.remote_uuid:
                tenant.handover_text = (
                    "Le tenant « %s » n'existe pas encore sur Wazo : créez-le, "
                    "puis ses coordonnées seront écrites ici." % tenant.name
                )
                continue
            tenant.handover_text = ENTETE_REMISE % {
                "nom": tenant.name,
                "url": url or "(à renseigner)",
                "jeton": tenant.api_token or "(aucun)",
                "tenant": tenant.remote_uuid,
                # Jamais de nom deviné ici : une fiche de remise qui donne un
                # contexte que Wazo ne connaît pas envoie le client au mauvais
                # endroit, sans que rien ne le signale.
                "contexte": tenant.remote_context_name or "(inconnu — à lire sur le serveur Wazo)",
                "admin": tenant.admin_username,
                "mot_de_passe": tenant.admin_password or "(inconnu)",
                "expiration": (
                    fields.Datetime.to_string(tenant.token_expires_at)
                    if tenant.token_expires_at
                    else "sans date connue"
                ),
            }

    # ------------------------------------------------------------------
    # Contrôles locaux
    # ------------------------------------------------------------------

    @api.depends("slug")
    def _compute_context_name(self):
        for tenant in self:
            tenant.context_name = "ctx-%s-internal" % tenant.slug if tenant.slug else False

    @api.constrains("slug")
    def _check_slug_is_a_wazo_tenant_slug(self):
        """Le slug doit passer le motif de Wazo **avant** tout appel."""
        for tenant in self:
            slug = tenant.slug or ""
            if not slug:
                continue  # requis : le cas vide ne vient pas d'ici
            if len(slug) > self._WAZO_SLUG_MAX:
                raise ValidationError(
                    self.env._(
                        "L'identifiant d'un tenant est limité à %(max)d caractères par "
                        "Wazo (ici %(longueur)d) : « %(slug)s ».",
                        max=self._WAZO_SLUG_MAX,
                        longueur=len(slug),
                        slug=slug,
                    )
                )
            if not self._WAZO_SLUG_RE.match(slug):
                raise ValidationError(
                    self.env._(
                        "L'identifiant d'un tenant ne peut contenir que des "
                        "lettres non accentuées, des chiffres et « _ » : ni accent, "
                        "ni tiret, ni espace. Identifiant refusé : « %s ».",
                        slug,
                    )
                )

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
        reponse = client.auth("GET", "/tenants") or {}
        for item in reponse.get("items") or []:
            if item.get("uuid") and item.get("uuid") == item.get("parent_uuid"):
                return item["uuid"]
        return None

    # ------------------------------------------------------------------
    # Adoption
    # ------------------------------------------------------------------

    def _remonter_a_la_racine(self, client, tenant_uuid):
        """UUID de la racine, en partant du tenant donné.

        Le listage des tenants est **cloisonné** par l'en-tête reçu : partir du
        tenant des réglages ne montrerait que lui et ses enfants, et laisserait
        le maître — donc les autres clients — invisibles.

        L'en-tête doit viser le tenant **interrogé** : un tenant parent est hors
        du sous-arbre du tenant courant, et sa fiche répond 404 si l'on garde
        l'en-tête d'origine (mesuré en direct, « unknown-tenant » — ce n'est pas
        un refus de permission mais du cloisonnement). On interroge donc chaque
        tenant avec son propre en-tête.

        Un tenant racine est son propre parent : c'est le seul repère sûr, le
        champ « parent » n'existant pas côté API. La remontée est bornée, et une
        fiche injoignable arrête la recherche sans faire échouer l'adoption.
        """
        identifiant = tenant_uuid
        for _ in range(10):
            if not identifiant:
                return tenant_uuid
            try:
                fiche = self._client(identifiant).auth("GET", "/tenants/%s" % identifiant) or {}
            except WazoAPIError:
                # Cloisonnement ou panne : on ne devine pas l'arborescence, on
                # liste avec ce que l'en-tête laisse voir.
                return identifiant
            if not isinstance(fiche, dict):
                return identifiant
            parent = fiche.get("parent_uuid")
            if not parent or parent == identifiant:
                return identifiant
            identifiant = parent
        return identifiant

    @api.model
    def _slug_local(self, slug, name, pris=None):
        """Identifiant acceptable par le modèle, tiré de ce que Wazo renvoie.

        Wazo accepte des slugs plus larges que notre contrainte locale (tirets,
        jusqu'à 80 caractères) : un tenant adopté ne doit pas faire échouer la
        création de sa fiche. Le nom réel reste dans ``name``, et
        ``remote_uuid`` est la vraie clé de rapprochement.
        """
        base = re.sub(r"[^a-zA-Z0-9_]", "_", slug or name or "tenant")
        base = base[: self._WAZO_SLUG_MAX] or "tenant"
        if not pris or base not in pris:
            return base
        for suffixe in range(2, 100):
            candidat = "%s_%d" % (base[: self._WAZO_SLUG_MAX - len(str(suffixe)) - 1], suffixe)
            if candidat not in pris:
                return candidat
        return base

    def _lire_contexte(self, identifiant, slug):
        """Nom réel du contexte interne d'un tenant, lu avec **son** en-tête.

        Wazo ajoute un suffixe au nom demandé : « ctx-<slug>-internal » devient
        « ctx-<slug>-internal-<aléa> ». Le nom calculé localement n'est donc
        qu'une approximation, et le publier dans la fiche de remise enverrait le
        client au mauvais contexte. On lit donc la vérité sur le PBX ; si elle
        reste hors d'atteinte, le champ demeure vide et la fiche dira
        « inconnu » plutôt que d'inventer.

        Le rapprochement se fait sur le préfixe, jamais sur le nom exact — c'est
        précisément le suffixe qui est en jeu.
        """
        try:
            reponse = self._client(identifiant).conf("GET", "/contexts") or {}
        except WazoAPIError:
            return {}
        items = (reponse.get("items") if isinstance(reponse, dict) else reponse) or []
        contextes = [item for item in items if isinstance(item, dict) and item.get("name")]
        prefixe = "ctx-%s-internal" % slug
        retenus = [item for item in contextes if item["name"].startswith(prefixe)]
        if not retenus:
            retenus = [item for item in contextes if "internal" in item["name"]]
        return retenus[0] if retenus else {}

    @api.model
    def action_adopt_from_wazo(self):
        """Fait entrer dans Odoo les tenants déjà présents sur le PBX.

        **Lecture seule côté PBX** : rien n'y est créé ni modifié. Les secrets
        d'un tenant — jeton d'API, mot de passe administrateur — ne sont jamais
        rendus par l'API : une fiche adoptée arrive donc sans eux. Ils se
        ressaisissent depuis la fiche de remise, ou s'obtiennent par
        « Renouveler le jeton », qui a besoin des identifiants administrateur
        du tenant.

        Les fiches déjà connues (même ``remote_uuid``) ne sont **pas** touchées :
        écraser un jeton vivant serait le pire effet de bord possible.
        """
        client = self._client()
        racine = self._remonter_a_la_racine(client, client.tenant_id)
        reponse = self._client(racine).auth("GET", "/tenants") or {}
        distants = (reponse.get("items") if isinstance(reponse, dict) else reponse) or []
        par_uuid = {
            tenant["uuid"]: tenant
            for tenant in distants
            if isinstance(tenant, dict) and tenant.get("uuid")
        }

        connus = {
            tenant.remote_uuid: tenant for tenant in self.search([("remote_uuid", "!=", False)])
        }
        # Tous les identifiants déjà pris, sans limite : un seul oublié et
        # l'adoption créerait un doublon.
        pris = set(self.search([]).mapped("slug"))  # pylint: disable=no-search-all
        adoptes, ignores = {}, 0
        for identifiant, distant in sorted(par_uuid.items()):
            if identifiant in connus:
                ignores += 1
                continue
            slug = self._slug_local(distant.get("slug"), distant.get("name"), pris)
            pris.add(slug)
            adoptes[identifiant] = self.create(
                {
                    "name": (distant.get("name") or distant.get("slug") or identifiant),
                    "slug": slug,
                    "remote_uuid": identifiant,
                    "state": "created",
                }
            )
        # Le nom réel du contexte se lit ensuite, tenant par tenant : Wazo le
        # suffixe, et une fiche adoptée doit porter la vraie valeur — c'est
        # celle que le client devra reporter dans wazo_phone.
        for identifiant, fiche in adoptes.items():
            contexte = self._lire_contexte(identifiant, fiche.slug)
            if contexte:
                fiche.remote_context_name = contexte.get("name")
        # Le rattachement se fait en second passage : un enfant peut précéder son
        # parent dans la réponse, et le parent peut n'être adopté qu'à ce tour.
        for identifiant, fiche in adoptes.items():
            distant = par_uuid.get(identifiant) or {}
            parent_uuid = distant.get("parent_uuid")
            if not parent_uuid or parent_uuid == identifiant:
                continue
            parent = adoptes.get(parent_uuid) or connus.get(parent_uuid)
            if parent:
                fiche.parent_id = parent.id
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if adoptes else "info",
                "title": "Adoption des tenants du PBX",
                "message": (
                    "%d tenant(s) adopté(s), %d déjà connu(s). Les jetons et "
                    "mots de passe ne sont pas rendus par l'API : "
                    "ressaisissez-les, ou renouvelez le jeton." % (len(adoptes), ignores)
                ),
                "sticky": False,
            },
        }

    @staticmethod
    def _mot_de_passe():
        """Mot de passe d'administration : alphanumérique, donc sans surprise.

        Ni accent, ni symbole : il traverse une API et sera recopié à la main
        par le tenant. Il n'est pas tiré d'un dictionnaire non plus.
        """
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(24))

    @staticmethod
    def _vers_datetime(horodatage):
        """Date ISO de Wazo vers date Odoo (naïve, en temps universel)."""
        if not horodatage:
            return False
        try:
            # Odoo range ses dates en UTC naïf : c'est la convention que
            # respecte ce convertisseur, et un fuseau ici la contredirait.
            return datetime.strptime(  # noqa: DTZ007
                str(horodatage)[:19], "%Y-%m-%dT%H:%M:%S"
            )
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
        if self.state == "created":
            raise UserError(
                self.env._(
                    "Le tenant « %s » existe déjà sur Wazo. Pour le reprendre, "
                    "supprimez-le d'abord ou créez-en un autre.",
                    self.name,
                )
            )
        client = self._client()
        # Un tenant déjà connu (reprise) se relit ; un tenant créé à l'instant
        # n'a rien à relire — et ne doit surtout pas être recréé.
        nouveau = not self.remote_uuid
        try:
            # 1. Le tenant, rattaché à la racine ou au parent déclaré. Il n'est
            #    créé qu'une fois : le recréer après un échec ferait un doublon
            #    sur le PBX, avec deux tenants du même nom.
            if not self.remote_uuid:
                corps = {"name": self.name, "slug": self.slug}
                parent = self.parent_id.remote_uuid or self._racine(client)
                if parent:
                    corps["parent_uuid"] = parent
                reponse = client.auth("POST", "/tenants", body=corps) or {}
                self.remote_uuid = reponse.get("uuid")
                if not self.remote_uuid:
                    raise WazoAPIError("Wazo n'a pas rendu l'identifiant du tenant créé.")
            client_tenant = self._client(self.remote_uuid)

            # 2. Le contexte et ses plages, dans le tenant. Repris s'il existe
            #    déjà — la réponse d'un premier appel a pu se perdre —, créé
            #    sinon. Les bornes sont transmises en texte, comme Wazo les rend.
            contexte = None
            if self.context_id:
                contexte = {"id": self.context_id, "name": self.remote_context_name}
            elif not nouveau:
                contexte = self._contexte_existant(client_tenant)
            if not contexte:
                contexte = (
                    client_tenant.conf(
                        "POST",
                        "/contexts",
                        body={
                            "label": self.context_name,
                            "user_ranges": [
                                {"start": self.user_range_start, "end": self.user_range_end}
                            ],
                            "group_ranges": [
                                {"start": self.group_range_start, "end": self.group_range_end}
                            ],
                        },
                    )
                    or {}
                )
            self.context_id = contexte.get("id") or 0
            self.remote_context_name = contexte.get("name") or self.context_name

            # 3. L'administrateur du tenant : créé **dans** le tenant (paramètre
            #    et en-tête), puis doté de la politique d'administration.
            # C'est l'en-tête du tenant qui fait foi : wazo-auth **ignore** le
            # paramètre `tenant_uuid` passé en chaîne de requête (mesuré en
            # direct), et un utilisateur créé sans en-tête naîtrait dans le
            # maître — le tenant se retrouverait sans administrateur.
            if not self.admin_user_uuid:
                utilisateur = None if nouveau else self._administrateur_existant(client_tenant)
                if utilisateur:
                    self.admin_user_uuid = utilisateur.get("uuid")
                else:
                    mot_de_passe = self.admin_password or self._mot_de_passe()
                    utilisateur = (
                        client_tenant.auth(
                            "POST",
                            "/users",
                            params={"tenant_uuid": self.remote_uuid},
                            body={
                                "username": self.admin_username,
                                "password": mot_de_passe,
                                "firstname": "Administrateur",
                                "lastname": self.name[:40],
                            },
                        )
                        or {}
                    )
                    self.admin_user_uuid = utilisateur.get("uuid")
                    self.admin_password = mot_de_passe
                if not self.admin_user_uuid:
                    raise WazoAPIError("Wazo n'a pas rendu l'identifiant de l'administrateur créé.")
            if not self.admin_password:
                # Un administrateur repris sans son mot de passe ne peut pas
                # recevoir de jeton : wazo-auth ne le rend à personne. Mieux
                # vaut le dire que de laisser un tenant sans accès.
                raise WazoAPIError(
                    "L'administrateur « %s » existe déjà sur Wazo mais son mot "
                    "de passe est inconnu de cette base : supprimez le tenant "
                    "sur Wazo, puis relancez la création." % self.admin_username
                )
            politique = self._politique_admin(client)
            if politique:
                client_tenant.auth(
                    "PUT", "/users/%s/policies/%s" % (self.admin_user_uuid, politique)
                )

            # 4. Son jeton, en Basic : les identifiants, pas le jeton du maître.
            donnees = client.token(
                self.admin_username, self.admin_password, expiration=self._TOKEN_EXPIRATION
            )
            self.api_token = donnees.get("token")
            self.token_expires_at = self._vers_datetime(donnees.get("expires_at"))
            self.state = "created"
            self.error_message = False
            return True
        except WazoAPIError as erreur:
            self.state = "error"
            self.error_message = str(erreur)
            return False

    def _contexte_existant(self, client_tenant):
        """Le contexte du tenant, s'il a déjà été créé (reprise).

        Un ``POST`` dont la réponse s'est perdue laisse un contexte sans trace
        locale : le recréer produirait un doublon invisible depuis Odoo. On
        relit donc la liste du tenant et on reconnaît le contexte à son
        étiquette — la seule que nous ayons posée.
        """
        reponse = client_tenant.conf("GET", "/contexts") or {}
        for item in reponse.get("items") or []:
            if item.get("label") == self.context_name:
                return item
        return None

    def _administrateur_existant(self, client_tenant):
        """L'administrateur du tenant, s'il a déjà été créé (reprise)."""
        reponse = client_tenant.auth("GET", "/users") or {}
        for item in reponse.get("items") or []:
            if item.get("username") == self.admin_username:
                return item
        return None

    def _politique_admin(self, client):
        """UUID de la politique d'administration, résolu depuis son slug.

        L'association attend un UUID, le slug est stable et lisible : c'est le
        slug qui est retenu ici, résolu à chaque création.
        """
        reponse = client.auth("GET", "/policies") or {}
        for item in reponse.get("items") or []:
            if item.get("slug") == self._POLITIQUE_ADMIN:
                return item.get("uuid")
        return None

    # ------------------------------------------------------------------
    # Suppression
    # ------------------------------------------------------------------

    def action_rotate_token(self):
        """Remplace le jeton d'un tenant **vivant**, puis révoque l'ancien.

        Le jeton est le secret remis au client. Le jour où il part — sauvegarde
        d'Odoo, poste de travail, employé qui quitte —, il faut pouvoir le
        remplacer : sans cette action, la seule sortie est de supprimer le
        tenant, ce que la garde refuse tant qu'il porte des postes, et qui
        emporterait le client avec elle.

        L'ordre est **émettre, puis révoquer** : une révocation ratée laisse
        deux jetons vivants — l'ancien mourra à son expiration — plutôt qu'un
        client dont le jeton vient d'être tué avant que son Odoo ait reçu le
        neuf. Et une révocation ratée est **dite** sur la fiche : c'est un
        secret qui reste valable, l'exploitant doit le savoir, pas le découvrir.
        """
        self.ensure_one()
        if not self.remote_uuid:
            raise UserError(
                self.env._(
                    "Le tenant « %s » n'existe pas encore sur Wazo : il n'y a pas "
                    "de jeton à renouveler.",
                    self.name,
                )
            )
        if not (self.admin_username and self.admin_password):
            raise UserError(
                self.env._(
                    "Le renouvellement se fait avec les identifiants de "
                    "l'administrateur du tenant, et Wazo ne rend jamais un mot de "
                    "passe : renseignez-les sur cette fiche."
                )
            )
        ancien = self.api_token
        client = self._client(self.remote_uuid)
        donnees = (
            client.token(
                self.admin_username, self.admin_password, expiration=self._TOKEN_EXPIRATION
            )
            or {}
        )
        if not donnees.get("token"):
            raise UserError(
                self.env._(
                    "Wazo n'a pas rendu de jeton pour « %s » : l'ancien reste en place.", self.name
                )
            )
        self.write(
            {
                "api_token": donnees["token"],
                "token_expires_at": self._vers_datetime(donnees.get("expires_at")),
                "token_rotated_at": fields.Datetime.now(),
                "previous_token_revoked": False,
                "token_revocation_note": False,
            }
        )
        if not ancien:
            return True
        try:
            client.revoke_token(ancien)
        except WazoAPIError as erreur:
            # La note est lue par des humains : le jeton ne s'y recopie pas, et
            # le journal se contente du code HTTP.
            _logger.warning(
                "Jeton du tenant « %s » non révoqué (HTTP %s) : il reste "
                "valable jusqu'à son expiration.",
                self.name,
                getattr(erreur, "status", "?"),
            )
            self.write(
                {
                    "token_revocation_note": (
                        "L'ancien jeton n'a pas pu être révoqué : il reste valable "
                        "jusqu'à son expiration. Réessayez, ou révoquez-le depuis "
                        "Wazo."
                    )
                }
            )
            return True
        self.write({"previous_token_revoked": True})
        return True

    def action_delete_on_wazo(self):
        """Supprime le tenant — après avoir vérifié qu'il ne porte plus rien.

        Trois appels, dans cet ordre : le contexte **du** tenant, son
        administrateur, puis le tenant. Supprimer le tenant d'abord rendrait
        son contexte inaccessible et laisserait un orphelin sur le PBX ; c'est
        la leçon des groupes d'appel (P4.3), où un échec en milieu de séquence
        avait laissé une trace sans propriétaire.
        """
        self.ensure_one()
        if self.state != "created" or not self.remote_uuid:
            raise UserError(
                self.env._(
                    "Le tenant « %s » n'existe pas sur Wazo : il n'y a rien à supprimer.", self.name
                )
            )
        client_tenant = self._client(self.remote_uuid)
        postes = (client_tenant.conf("GET", "/users") or {}).get("total") or 0
        lignes = (client_tenant.conf("GET", "/lines") or {}).get("total") or 0
        if postes or lignes:
            raise UserError(
                self.env._(
                    "Le tenant « %(tenant)s » porte encore %(postes)d poste(s) et "
                    "%(lignes)d ligne(s) : supprimez-les depuis l'instance Odoo du "
                    "tenant avant de supprimer son tenant.",
                    tenant=self.name,
                    postes=postes,
                    lignes=lignes,
                )
            )
        if self.context_id:
            client_tenant.conf("DELETE", "/contexts/%s" % self.context_id)
        if self.admin_user_uuid:
            self._client().auth("DELETE", "/users/%s" % self.admin_user_uuid)
        self._client().auth("DELETE", "/tenants/%s" % self.remote_uuid)
        self.write(
            {
                "state": "new",
                "remote_uuid": False,
                "context_id": 0,
                "remote_context_name": False,
                "admin_user_uuid": False,
                "admin_password": False,
                "api_token": False,
                "token_expires_at": False,
                "error_message": False,
            }
        )
        return True
