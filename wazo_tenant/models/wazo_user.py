# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Miroir local des utilisateurs Wazo et opérations de synchronisation.

Le flux de création suit le schéma de la Wazo Platform 26
(wazo-confd API v1.1) :

1. ``POST /extensions`` — le poste (sauf s'il existe déjà)
2. ``POST /lines`` — la ligne SIP, portant en son body :

   * ``context`` : le contexte Wazo
   * ``extensions`` : la liste des postes associés ``[{id: ...}]``
   * ``endpoint_sip`` : le dict d'endpoint SIP contenant
     ``auth_section_options: [["username", "…"]]``
3. ``POST /users`` — l'utilisateur (prénom / nom)
4. ``PUT /users/{id}/lines/{id}`` — associer l'utilisateur à la ligne
5. ``POST /voicemails`` — la messagerie vocale
6. ``PUT /users/{id}/voicemails/{id}`` — associer la messagerie
7. ``POST /api/auth/0.1/users`` — créer le compte SIP d'authentification
   (mot de passe de registration, géré par ``authd``)

Le flux est idempotent pour le poste (réutilisé s'il existe déjà) ;
les autres ressources sont réconciliées par les identifiants distants
enregistrés sur ``wazo.user``.

Chaque écriture distante est définitive même si la transaction Odoo
est annulée par la suite : en cas d'erreur en cours de flux, le
message d'erreur précise l'étape échouée.
"""

import logging

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..services.wazo_client import WazoAPIError

_logger = logging.getLogger(__name__)

#: Options d'endpoint SIP du repli local quand les templates du tenant
#: ne sont pas résolus : codec navigateur, ICE, chiffrement DTLS et
#: média direct. Le transport ``wss`` est hérité de l'endpoint.
WEBRTC_ENDPOINT_OPTIONS = [
    ["allow", "opus,g722,alaw,ulaw,vp9,vp8,h264"],
    ["ice_support", "yes"],
    ["use_avpf", "yes"],
    ["media_encryption", "dtls"],
    ["dtls_verify", "no"],
    ["direct_media", "yes"],
]


class WazoUser(models.Model):
    _name = "wazo.user"
    #: Postes, contrôle de plage, recherche côté Wazo : voir le mixin.
    _inherit = ["wazo.extension.mixin"]
    _extension_type = "user"
    _description = "Utilisateur Wazo"
    _rec_name = "name"

    name = fields.Char(string="Nom", required=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        ondelete="set null",
        index=True,
        help="Contact Odoo associé à cet utilisateur Wazo.",
    )
    wazo_state = fields.Selection(
        selection=[
            ("new", "Nouveau"),
            ("synced", "Synchronisé"),
            ("error", "Erreur"),
        ],
        string="État",
        default="new",
        required=True,
    )
    remote_user_id = fields.Char(
        string="ID utilisateur Wazo",
        help="Identifiant de l'utilisateur côté Wazo (confd 1.1) : celui qui "
        "figure dans les URL, distinct de son UUID.",
    )
    remote_user_uuid = fields.Char(
        string="UUID utilisateur Wazo",
        help="UUID de l'utilisateur côté Wazo. C'est lui que réclament les "
        "associations par utilisateur — membres d'un groupe d'appel, "
        "notamment.",
    )
    remote_line_id = fields.Integer(string="ID ligne Wazo")
    remote_extension_id = fields.Integer(string="ID poste Wazo")
    sip_username = fields.Char(string="Identifiant SIP")
    sip_password = fields.Char(string="Mot de passe SIP", groups="wazo_tenant.group_wazo_manager")
    remote_sip_id = fields.Char(
        string="UUID compte SIP (authd)",
        help="Identifiant (UUID) du compte d'authentification SIP côté "
        "authd (service d'authentification Wazo).",
    )
    remote_endpoint_name = fields.Char(
        string="Nom de l'endpoint SIP (AOR)",
        readonly=True,
        copy=False,
        help="Nom de l'endpoint SIP côté Wazo — l'AOR, donc le nom "
        "d'authentification du REGISTER. Confondu avec l'extension une fois, "
        "le REGISTER était refusé : il est consigné à part.",
    )
    error_message = fields.Text(string="Dernier message d'erreur")
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------------
    # Synchronisation vers Wazo
    # ------------------------------------------------------------------

    @api.model
    def _get_sip_template_uuids(self, client):
        """Résout les UUID des templates SIP du tenant Wazo.

        ``GET /tenants/<uuid>`` porte ``global_sip_template_uuid`` et
        ``webrtc_sip_template_uuid``. Résolu en direct plutôt que mis en
        cache : l'UUID change si le tenant est réinitialisé, et le coût
        est un simple GET de configuration.

        Défensif : retourne ``{}`` (donc repli sur les options locales) si
        le tenant n'est pas configuré, si l'appel échoue, ou si la réponse
        n'a pas la forme attendue. Une synchronisation ne doit jamais
        échouer parce qu'un template n'a pas pu être résolu.
        """
        tenant_uuid = getattr(client, "tenant_id", False)
        if not tenant_uuid:
            return {}
        try:
            tenant = client.conf("GET", "/tenants/%s" % tenant_uuid)
        except WazoAPIError:
            return {}
        if not isinstance(tenant, dict):
            return {}
        return {
            "global": tenant.get("global_sip_template_uuid") or False,
            "webrtc": tenant.get("webrtc_sip_template_uuid") or False,
        }

    @api.model
    def _build_endpoint_sip_payload(self, context, extension, templates=None):
        """Construit le payload ``endpoint_sip`` WebRTC-capable.

        Voie native (spec P3 v3) : lorsque les templates SIP du tenant
        sont connus (``global`` + ``webrtc``, voir
        ``_get_sip_template_uuids``), l'endpoint s'y **réfère**. Les
        options WebRTC (``webrtc=yes``, codecs, ICE/AVPF/DTLS, transport
        ``wss``) viennent alors de Wazo lui-même, au lieu d'une réplique
        locale qui dérive à chaque évolution de la plateforme — la
        réplique ``WEBRTC_ENDPOINT_OPTIONS`` avait ainsi déjà perdu
        ``webrtc=yes`` et contredisait ``direct_media``.

        Le ``context``, lui, n'est porté par aucun des deux templates : il
        reste explicite sur l'endpoint.

        Sans template résolu (résolution impossible), on retombe sur la
        réplique locale afin de ne jamais créer silencieusement un
        endpoint non-WebRTC.

        Factorisé ici afin que la logique soit testable et réutilisable par
        le flux de synchronisation.
        """
        endpoint_sip = {
            "auth_section_options": [
                ["username", str(extension)],
            ],
            "endpoint_section_options": [
                ["context", str(context)],
            ],
        }
        # L'ordre est significatif : ``global`` d'abord, ``webrtc``
        # ensuite (le second surcharge le premier).
        sip_templates = [
            {"uuid": uuid}
            for uuid in (
                (templates or {}).get("global"),
                (templates or {}).get("webrtc"),
            )
            if uuid
        ]
        if sip_templates:
            endpoint_sip["templates"] = sip_templates
        else:
            endpoint_sip["endpoint_section_options"] += [
                list(option) for option in WEBRTC_ENDPOINT_OPTIONS
            ]
        return {"endpoint_sip": endpoint_sip}

    def _find_remote_line(self, client):
        """Retourne la ligne Wazo de l'utilisateur, ou ``None``.

        Par son id quand on le connaît (cas normal), sinon en la retrouvant par
        le poste — utile pour une fiche synchronisée avant que l'id soit
        conservé.
        """
        if self.remote_line_id:
            return client.conf("GET", "/lines/%s" % self.remote_line_id)
        reponse = client.conf("GET", "/lines", params={"exten": self.extension})
        items = reponse.get("items") if isinstance(reponse, dict) else reponse
        for item in items or []:
            if str(item.get("exten")) == str(self.extension):
                return client.conf("GET", "/lines/%s" % item["id"])
        return None

    def _ensure_remote_user_uuid(self, client=None):
        """Rend l'uuid Wazo de l'utilisateur, en le relisant au besoin.

        ``remote_user_uuid`` est né avec les groupes d'appel : un utilisateur
        synchronisé **avant** porte un uuid vide, et son état ``synced``
        interdit de le resynchroniser. Sans cette relecture, il ne pourrait
        jamais être membre d'un groupe. L'uuid se lit sur la ligne
        (``Line.users``) : rien n'est recréé, rien n'est modifié côté PBX.
        """
        self.ensure_one()
        if self.remote_user_uuid:
            return self.remote_user_uuid
        if self.wazo_state != "synced":
            # Rien n'existe au PBX sous cette fiche : pas d'uuid à relire.
            return False
        client = client or self._wazo_client()
        ligne = self._find_remote_line(client)
        for proprietaire in (ligne or {}).get("users") or []:
            if proprietaire.get("uuid"):
                self.sudo().write({"remote_user_uuid": proprietaire["uuid"]})
                return proprietaire["uuid"]
        return False

    def _wazo_voicemail_language(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_str("wazo.voicemail_language", default="fr_CA")
            or "fr_CA"
        )

    def _endpoint_name_from_line(self, line):
        """Retourne le nom de l'endpoint (l'AOR) porté par une réponse ``/lines``.

        La forme a changé selon les versions : tantôt le nom directement,
        tantôt l'**objet complet** de l'endpoint. Mesuré en direct sur Wazo
        26 : l'objet, son nom étant sous ``name``. Écrire autre chose que le
        nom dans ``remote_endpoint_name`` — qui est l'AOR, donc l'en-tête
        ``From`` du softphone — produit un en-tête invalide et un poste muet,
        sans la moindre erreur côté serveur.
        """
        endpoint = line.get("endpoint_sip") or {}
        if isinstance(endpoint, dict):
            return endpoint.get("name") or False
        return endpoint or False

    def action_sync_wazo(self):
        """Crée (ou reprend) l'utilisateur et ses ressources sur Wazo."""
        self.ensure_one()
        if self.wazo_state == "synced":
            raise UserError(
                self.env._("L'utilisateur %s est déjà synchronisé sur Wazo.", self.name)
            )
        if not self.extension:
            raise UserError(
                self.env._("Le poste téléphonique est requis avant de synchroniser sur Wazo.")
            )
        client = self._wazo_client()
        context = self._wazo_line_context()
        # Mot de passe SIP de registration, généré localement puis stocké
        # dans la base (le champ n'est jamais relu côté authd).
        import secrets

        sip_password = secrets.token_urlsafe(24)
        parts = (self.name or "").split()
        firstname = parts[0] if parts else "Utilisateur"
        lastname = " ".join(parts[1:])
        try:
            # 1. Poste : réutilisé s'il existe déjà (reprise idempotente).
            #    La recherche ne dépend pas du filtre serveur (parcours
            #    complet en secours) : certains environnements ne
            #    retournent pas la liste filtrée attendue.
            extension = self._find_wazo_extension(client)
            # Contrôle du poste saisi (plage, type, disponibilité) : refus
            # AVANT toute écriture distante.
            self._check_extension_allowed(client, context, extension)
            if extension is None:
                try:
                    extension = client.conf(
                        "POST", "/extensions", body={"exten": self.extension, "context": context}
                    )
                except WazoAPIError:
                    # Conflit « déjà existe » : on la re-cherche (le
                    # filtre serveur a pu manquer au premier coup).
                    extension = self._find_wazo_extension(client)
                    if extension is None:
                        raise
            # 2. Templates SIP du tenant (``global`` + ``webrtc``) : le
            #    softphone s'inscrit sur un endpoint WebRTC dont les
            #    options viennent de ces templates — on ne les
            #    réimplémente pas (spec P3 v3, section NORMATIF : voie
            #    native, sans relay).
            templates = self._get_sip_template_uuids(client)
            # 3. Ligne SIP (Wazo 26 : POST /lines, body complet avec
            #    extensions (référencées par leur numéro) + endpoint_sip
            #    WebRTC-capable (auth username + templates du tenant, voir
            #    le pont softphone : _build_endpoint_sip_payload).
            line = client.conf(
                "POST",
                "/lines",
                body={
                    "context": context,
                    "extensions": [{"exten": self.extension}],
                    **self._build_endpoint_sip_payload(context, self.extension, templates),
                },
            )
            # 4. Utilisateur.
            user = client.conf(
                "POST",
                "/users",
                body={
                    "firstname": firstname,
                    "lastname": lastname,
                },
            )
            # 5. Associer l'utilisateur à la ligne (plugin ``user_line``).
            client.conf("PUT", "/users/%s/lines/%s" % (user["id"], line["id"]))
            # L'endpoint PJSIP reçoit son nom d'AOR généré (ex. ``yoo0d0tp``) :
            # l'enregistrement SIP identifie l'endpoint par l'URI du REGISTER
            # **et** le digest par ``auth_section_options.username`` — les deux
            # doivent être ce nom, sinon asterisk refuse le REGISTER.
            try:
                endpoint = client.conf("GET", "/endpoints/sip/%s" % line["endpoint_sip"]["uuid"])
                client.conf(
                    "PUT",
                    "/endpoints/sip/%s" % line["endpoint_sip"]["uuid"],
                    body={
                        "auth_section_options": [
                            ["username", endpoint["name"]],
                            ["password", sip_password],
                        ],
                    },
                )
            except (KeyError, TypeError, WazoAPIError):
                _logger.warning(
                    "wazo.user %s: impossible d'aligner l'auth SIP de l'endpoint",
                    self.id,
                )
            # 6-7. Messagerie vocale + association.
            voicemail = client.conf(
                "POST",
                "/voicemails",
                body={
                    "name": self.name,
                    "number": self.extension,
                    "context": context,
                    "language": self._wazo_voicemail_language(),
                },
            )
            client.conf("PUT", "/users/%s/voicemails/%s" % (user["id"], voicemail["id"]))
            # 8. Compte SIP d'authentification (authd) : nom d'utilisateur
            #    = le poste, mot de passe de registration connu.
            #    Le re-sync est idempotent : un compte déjà existant
            #    (HTTP 409) est simplement récupéré par sa clé unique
            #    (username), sans doubler la ressource.
            try:
                sip_auth = client.auth(
                    "POST",
                    "/users",
                    body={
                        "username": self.extension,
                        "password": sip_password,
                    },
                )
            except WazoAPIError as e:
                if e.status != 409:
                    raise
                existing = client.auth("GET", "/users", params={"username": self.extension})
                items = existing.get("items") if isinstance(existing, dict) else existing
                for sip_auth in items or []:
                    if sip_auth.get("username") == self.extension:
                        break
                else:
                    sip_auth = {}
        except UserError:
            # Un refus de validation (poste hors plage, réservé à un autre type,
            # déjà attribué) s'adresse à l'utilisateur : il remonte tel quel au
            # lieu d'être transformé en état d'erreur silencieux, et rien n'a
            # été créé sur Wazo.
            raise
        except Exception as error:  # noqa: BLE001 - consigner plutôt que remonter
            # L'échec est consigné sur la ligne (état 'Erreur' + message
            # visible dans le formulaire) plutôt que de remonter l'exception :
            # le rollback transactionnel effacerait sinon l'état d'erreur.
            # L'utilisateur corrige la configuration et relance la synchro.
            self.write(
                {
                    "wazo_state": "error",
                    "error_message": str(error),
                }
            )
            return False
        self.sudo().write(
            {
                "wazo_state": "synced",
                "remote_user_id": user["id"],
                # L'uuid sert aux associations par utilisateur (membres d'un
                # groupe d'appel) : l'id, lui, sert aux URL.
                "remote_user_uuid": user.get("uuid"),
                "remote_line_id": line["id"],
                "remote_extension_id": extension["id"],
                # Nom d'endpoint SIP généré par Wazo confgen (= l'AOR du
                # softphone, en-tête From — découverte P3.2 : distinct de
                # l'extension).
                "remote_endpoint_name": self._endpoint_name_from_line(line),
                "sip_username": self.extension,
                "sip_password": sip_password,
                "remote_sip_id": sip_auth.get("uuid"),
                "error_message": False,
            }
        )
        # Pont softphone (module « voip » d'Enterprise) : propage les
        # identifiants SIP vers l'utilisateur Odoo lié. Cette étape est
        # non bloquante (les échecs internes sont consignés dans les
        # logs, voir voip_bridge).
        self._propagate_voip_credentials()
        return True

    def action_delete_wazo(self):
        """Supprime les ressources Wazo associées (ordre sûr, idempotent).

        Wazo 26 : l'utilisateur ne peut être supprimé que s'il n'est plus
        lié à une ligne ni à une messagerie vocale. On donc :

        1. détruire la messagerie vocale du poste (si elle existe) ;
        2. supprimer l'utilisateur (ses lignes et messageries vocales
           étant alors dissociées) ;
        3. supprimer la ligne (``recursive=true`` : retire endpoint SIP,
           extensions et associations restantes) ;
        4. supprimer l'extension (poste) ;
        5. supprimer le compte SIP d'authentification (authd), par
           nom d'utilisateur.

        Chaque étape tolère l'absence de la ressource (404 ignoré), de
        sorte qu'une relance après un échec partiel nettoie proprement.
        Les ids du miroir servent de repère mais la suppression
        n'en dépend pas (l'état est reconstruit depuis Wazo).
        """
        self.ensure_one()
        client = self._wazo_client()

        def _ignore_404(method, path):
            try:
                client.conf(method, path)
            except WazoAPIError as error:
                if "HTTP 404" not in str(error):
                    raise
            return True

        try:
            # Ordre sûr (Wazo 26) : la ligne est d'abord supprimée en
            # récursif, ce qui retire son endpoint SIP, ses extensions et
            # ses associations à l'utilisateur. Une fois l'utilisateur
            # « détaché », on dissocie et supprime sa messagerie vocale,
            # puis l'utilisateur lui-même, enfin le compte SIP d'auth (authd).
            if self.remote_line_id:
                _ignore_404("DELETE", "/lines/%s?recursive=true" % self.remote_line_id)
            # Messagerie vocale du poste : dissociation de l'utilisateur
            # puis suppression (la messagerie ne peut être supprimée tant
            # qu'elle est encore associée à un utilisateur).
            if self.remote_user_id:
                _ignore_404("DELETE", "/users/%s/voicemails" % self.remote_user_id)
            vms = client.conf("GET", "/voicemails")
            items = vms.get("items") if isinstance(vms, dict) else vms
            for vm in items or []:
                if str(vm.get("number")) == str(self.extension):
                    _ignore_404("DELETE", "/voicemails/%s" % vm["id"])
            # Utilisateur.
            if self.remote_user_id:
                _ignore_404("DELETE", "/users/%s" % self.remote_user_id)
            # Extension.
            if self.remote_extension_id:
                _ignore_404("DELETE", "/extensions/%s" % self.remote_extension_id)
            # Compte SIP d'authentification (authd) : supprimé par son
            # UUID (la clé de l'API authd), pas par le nom
            # d'utilisateur.
            if self.remote_sip_id:
                client.auth("DELETE", "/users/%s" % self.remote_sip_id)
        except Exception as error:  # noqa: BLE001 - consigner plutôt que remonter
            # Comme à la synchronisation : on consigne l'échec sur la ligne
            # au lieu de remonter l'exception, pour que l'état d'erreur ne
            # soit pas effacé par le rollback transactionnel. Les
            # identifiants distants restants sont conservés pour la relance.
            self.write(
                {
                    "wazo_state": "error",
                    "error_message": str(error),
                }
            )
            return False
        # Pont softphone : révoque les identifiants SIP (s'ils
        # proviennent de Wazo), tant que les valeurs locales sont
        # encore en place. Non bloquant comme la propagation.
        self._revoke_voip_credentials()
        self.sudo().write(
            {
                "wazo_state": "new",
                "remote_user_id": False,
                "remote_line_id": False,
                "remote_extension_id": False,
                "sip_username": False,
                "sip_password": False,
                "remote_sip_id": False,
                "error_message": False,
            }
        )

    def action_retry_sync(self):
        """Relance la synchronisation après une erreur."""
        self.ensure_one()
        self.action_sync_wazo()

    # ------------------------------------------------------------------
    # Crochets du pont softphone
    # ------------------------------------------------------------------
    # Ces deux crochets sont des no-ops au niveau du tenant : c'est
    # ``wazo_phone`` (voip_bridge) qui les surcharge pour propager ou
    # révoquer les identifiants SIP vers l'utilisateur Odoo. Sans ces
    # no-ops, une installation tenant **seule** échouerait en silence à
    # chaque synchronisation — le large except de action_sync_wazo
    # transformerait l'AttributeError en état « error » inexpliqué.

    def _propagate_voip_credentials(self):
        """No-op : surchargé par wazo_phone (pont softphone)."""
        return True

    def _revoke_voip_credentials(self):
        """No-op : surchargé par wazo_phone (pont softphone)."""
        return True
