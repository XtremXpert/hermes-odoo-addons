# Part of the wazo_voipms Odoo module. See LICENSE for details.
"""Trunk SIP sortant : Wazo appelle le RTC via un sous-compte VoIP.ms.

Le flux de provisionnement :

1. VoIP.ms — ``createSubAccount`` (sauf si l'identifiant SIP est déjà saisi :
   un sous-compte existant peut être réutilisé tel quel) ;
2. Wazo — ``POST /endpoints/sip`` : endpoint de type trunk (AOR = le POP,
   ``outbound_auth`` = identifiants du sous-compte, section ``registration``
   pour l'enregistrement sortant) ;
3. Wazo — ``POST /trunks`` puis ``PUT /trunks/{id}/endpoints/sip/{uuid}`` ;
4. Wazo — ``POST /outcalls`` puis ``PUT /outcalls/{id}/trunks`` (corps : liste
   ``{"id": …}``) et ``PUT /outcalls/{id}/extensions/{id}`` pour le motif de
   numérotation (contexte ``to-extern``).

Chaque écriture distante est définitive même si la transaction Odoo est
annulée ensuite : en cas d'erreur en cours de flux, l'état ``error`` et le
message sont consignés sur la fiche, et la reprise est idempotent grâce aux
identifiants distants conservés.
"""

import re

from odoo import api
from odoo import fields
from odoo import models
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSAPIError
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient
from odoo.addons.wazo_tenant.services.wazo_client import WazoAPIError
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError


class WazoVoipmsTrunk(models.Model):
    _name = "wazo.voipms.trunk"
    _description = "Trunk SIP VoIP.ms ↔ Wazo"
    _order = "name"

    name = fields.Char(string="Nom", required=True)
    voipms_username = fields.Char(
        string="Identifiant SIP VoIP.ms",
        help="Nom d'utilisateur du sous-compte VoIP.ms (ex. 123456_odoo). "
        "Laisser vide pour en créer un au provisionnement.",
    )
    voipms_password = fields.Char(
        string="Mot de passe SIP VoIP.ms",
        groups="wazo_tenant.group_wazo_manager",
        help="Mot de passe SIP du sous-compte. Laisser vide pour qu'il soit "
        "généré au provisionnement.",
    )
    pop_host = fields.Char(
        string="Serveur (POP)",
        default="montreal1.voip.ms",
        required=True,
        help="Nom d'hôte du point de présence VoIP.ms (voir getServersInfo).",
    )
    caller_id = fields.Char(
        string="Indicatif d'appelant sortant",
        help="Numéro présenté au RTC (E.164, ex. 14184803381). Doit être un DID du compte VoIP.ms.",
    )
    outbound_prefix = fields.Char(
        string="Préfixe de sortie",
        default="9",
        help="Chiffre(s) à composer devant le numéro pour sortir par ce "
        "trunk (motif « _9. » dans le contexte to-extern).",
    )
    state = fields.Selection(
        selection=[
            ("new", "Nouveau"),
            ("synced", "Provisionné"),
            ("error", "Erreur"),
        ],
        string="État",
        default="new",
        required=True,
    )
    error_message = fields.Text(string="Dernier message d'erreur")
    #: Un sous-compte VoIP.ms est **mono-protocole** (mesuré :
    # « protocol » à la création, 1 = SIP, 3 = IAX2) : le choix fait ici
    # décide de la jambe Wazo <-> VoIP.ms — les usagers restent en
    # WebRTC/SIP vers le Wazo dans tous les cas.
    #: Le tenant propriétaire du trunk — et des DIDs qu'il porte.
    #: Maison (le serveur) voit tout ; l'Odoo d'un tenant ne route
    #: que les siens (mesuré : le design voulu — chaque DID se règle
    #: dans l'Odoo de SON tenant).
    tenant_slug = fields.Char(
        string="Slug du tenant propriétaire",
        help="Le DID routé par ce trunk appartient à ce tenant : son "
        "Odoo le configure, maison (le serveur) le voit.",
    )
    protocol = fields.Selection(
        selection=[
            ("sip", "SIP"),
            ("iax2", "IAX2"),
        ],
        string="Protocole",
        default="sip",
        required=True,
    )
    remote_endpoint_uuid = fields.Char(string="UUID endpoint SIP Wazo")
    remote_endpoint_iax_id = fields.Integer(string="ID endpoint IAX Wazo")
    remote_register_iax_id = fields.Integer(string="ID registration IAX Wazo")
    remote_trunk_id = fields.Integer(string="ID trunk Wazo")
    remote_outcall_id = fields.Integer(string="ID outcall Wazo")
    remote_outcall_extension_id = fields.Integer(string="ID motif outcall Wazo")
    registered = fields.Boolean(string="Enregistré", readonly=True)
    registered_label = fields.Selection(
        [("sip", "SIP"), ("iax2", "IAX2")],
        string="Protocole du statut",
        compute="_compute_registered_label",
    )
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint("unique(name)", "Ce nom de trunk existe déjà.")

    @api.constrains("outbound_prefix")
    def _check_outbound_prefix(self):
        for trunk in self:
            if trunk.outbound_prefix and not re.fullmatch(r"[0-9]+", trunk.outbound_prefix):
                raise ValidationError(self.env._("Le préfixe de sortie doit être numérique."))

    # ------------------------------------------------------------------
    # Côté Wazo
    # ------------------------------------------------------------------

    def _wazo_client(self):
        """Client scoped to THIS trunk's tenant, not the global parameter.

        The server instance (maison) routes trunks that live in different
        tenants: the ``Wazo-Tenant`` header must follow ``tenant_slug``,
        resolved through ``wazo.server.tenant`` when that module is around
        (it is not on tenant instances — the global param already fits).
        """
        # Import via le module du mixin — les tests y substituent
        # ``WazoClient`` par leur faux serveur routé.
        from odoo.addons.wazo_tenant.models import wazo_extension_mixin

        return wazo_extension_mixin.WazoClient(self.env, tenant_id=self._wazo_tenant_uuid())

    def _wazo_tenant_uuid(self):
        if self.tenant_slug:
            Tenant = self.env.get("wazo.server.tenant")
            if Tenant is not None:
                tenant = Tenant.sudo().search([("slug", "=", self.tenant_slug)], limit=1)
                if tenant and tenant.remote_uuid:
                    return tenant.remote_uuid
        return self.env["wazo.user"]._wazo_tenant_uuid()

    def _outcall_context(self):
        """Contexte des renvois sortants — ``to-extern`` sur Wazo 26."""
        return "to-extern"

    def _resolve_outcall(self, client, extension_id):
        """Id de l'outcall à utiliser : **le nôtre** par son nom,
        sinon celui qui possède déjà le motif, sinon un nouveau.

        Chaque trunk a besoin de sa propre outcall : une outcall
        partagée trie ses trunks par index, et l'appel d'un tenant
        partirait sur le compte VoIP.ms d'un autre — mesuré : le
        5001 d'xtremxpert sortait par le trunk de Diverse-Cité.
        Le repli par motif sert la reprise (extension créée avant
        l'outcall à une tentative antérieure).
        """
        response = client.conf("GET", "/outcalls")
        items = response.get("items") or [] if isinstance(response, dict) else []
        nom = "out-%s" % self.name
        for outcall in items:
            if outcall.get("name") == nom:
                return outcall["id"]
        for outcall in items:
            for extension in outcall.get("extensions") or []:
                if extension.get("id") == extension_id:
                    return outcall["id"]
        try:
            outcall = client.conf("POST", "/outcalls", body={"name": "out-%s" % self.name})
        except WazoAPIError as error:
            # Reprise : un outcall orphelin d'une tentative échouée est
            # repris par son nom (« Outcall already exists » sinon —
            # l'outcall survit au rollback Odoo, lui).
            if "already exists" not in str(error):
                raise
            for outcall in items:
                if outcall.get("name") == "out-%s" % self.name:
                    return outcall["id"]
            raise
        return outcall["id"]

    def _resolve_outcall_context(self, client):
        """Nom **réel** du contexte sortant, créé au besoin.

        Mesuré sur un Wazo neuf : le provisionnement d'un tenant ne crée
        que son contexte interne, et ``POST /extensions`` refuse un
        contexte inconnu (HTTP 400). Wazo 26 génère de plus un nom
        interne (``ctx-…-<uuid>``) : l'extension désigne le contexte
        par ce **nom**, pas par son libellé ``to-extern`` — d'où la
        résolution, et non l'écriture directe du libellé.
        """
        response = client.conf("GET", "/contexts")
        items = response.get("items") or [] if isinstance(response, dict) else []
        for item in items:
            if item.get("label") == self._outcall_context():
                self._ensure_outcall_include(client, items, item["id"])
                return item["name"]
        created = client.conf(
            "POST", "/contexts", body={"name": self._outcall_context(), "type": "outcall"}
        )
        self._ensure_outcall_include(client, items, created["id"])
        return created["name"]

    def _ensure_outcall_include(self, client, contexts, outcall_id):
        """Le contexte interne du tenant inclut le contexte sortant.

        Sans l'inclusion, un numéro externe ne matche aucun motif du
        contexte interne et asterisk répond 404 après l'auth — mesuré :
        l'INVITE mourrait une seconde après le 100 Trying. ``PUT
        /contexts/{id}/contexts`` remplace la liste : les inclusions
        existantes sont relues, puis l'outcall ajouté sans les perdre.
        """
        internal = next((item for item in contexts if item.get("type") == "internal"), None)
        if internal is None:
            response = client.conf("GET", "/contexts")
            items = response.get("items") or [] if isinstance(response, dict) else []
            internal = next((item for item in items if item.get("type") == "internal"), None)
        if internal is None:
            return
        detail = client.conf("GET", "/contexts/%s" % internal["id"]) or {}
        existing = [c["id"] for c in detail.get("contexts") or []]
        if outcall_id in existing:
            return
        client.conf(
            "PUT",
            "/contexts/%s/contexts" % internal["id"],
            body={"contexts": [{"id": i} for i in [*existing, outcall_id]]},
        )

    def _identify_options(self):
        """Options d'``identify`` : les IP du POP.

        Mesuré : l'INVITE de VoIP.ms arrive sans s'authentifier, et sans
        identify par IP, Asterisk ne le rattache à aucun endpoint — le
        rejet « Failed to authenticate » renvoie l'appel au fournisseur
        (« your call cannot be completed as dialed »).
        """
        import socket

        try:
            infos = socket.getaddrinfo(self.pop_host, 5060, socket.AF_INET, socket.SOCK_DGRAM)
        except OSError:
            return []
        ips = sorted({info[4][0] for info in infos})
        return [["match", ip] for ip in ips]

    def _endpoint_payload(self, client=None):
        """Corps ``POST /endpoints/sip`` : trunk enregistré sur le POP."""
        return {
            "name": "odoo-%s" % re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-"),
            "label": self.name,
            "aor_section_options": [["contact", "sip:%s" % self.pop_host]],
            "outbound_auth_section_options": [
                ["username", self.voipms_username],
                ["password", self.voipms_password],
            ],
            # La registration s'authentifie avec ses propres identifiants
            # — mesuré : sans cette section, le REGISTER part nu et
            # voip.ms le rejette (« Rejected » côté Asterisk).
            "registration_outbound_auth_section_options": [
                ["username", self.voipms_username],
                ["password", self.voipms_password],
            ],
            "registration_section_options": [
                ["client_uri", "sip:%s@%s" % (self.voipms_username, self.pop_host)],
                ["server_uri", "sip:%s" % self.pop_host],
                ["retry_interval", "60"],
                ["expiration", "120"],
                ["outbound_proxy", "sip:%s" % self.pop_host],
                # Wazo injecte « endpoint = <nom> » dans la registration
                # d'un trunk ; sans « line », Asterisk refuse l'objet
                # (mesuré : « without enabling line support »). Avec lui,
                # l'entrant du trunk passe par la registration.
                ["line", "true"],
            ],
            "identify_section_options": self._identify_options(),
            "endpoint_section_options": [
                # Mesuré : le contexte des renvois entrants se désigne par
                # son nom généré, pas par le libellé « from-extern ».
                ["context", self._resolve_incall_context(client)],
                ["from_user", self.caller_id or self.voipms_username],
            ],
        }

    def _resolve_incall_context(self, client):
        """Nom du contexte des renvois entrants, créé au besoin.

        Mesuré : « from-extern » est un libellé — Wazo 26 génère un nom
        interne, et c'est LUI que l'endpoint doit viser dans son option
        « context » : le libellé littéral pointe dans le vide du
        dialplan.
        """
        response = client.conf("GET", "/contexts")
        items = response.get("items") or [] if isinstance(response, dict) else []
        for item in items:
            if item.get("label") == "from-extern":
                return item["name"]
        created = client.conf("POST", "/contexts", body={"label": "from-extern", "type": "incall"})
        return created["name"]

    def _iax_endpoint_payload(self, client=None):
        """Corps ``POST /endpoints/iax`` : pair « friend » du POP.

        Mesuré : host = l'IP du POP (l'appel entrant de VoIP.ms s'y
        matche par IP), context = le contexte incall résolu — le
        libellé « from-extern » ne désigne rien en dialplan — et
        secret = le mot de passe du sous-compte, celui que VoIP.ms
        présente à l'arrivée.
        """
        import socket

        host = self.pop_host
        try:
            infos = socket.getaddrinfo(self.pop_host, 4569, socket.AF_INET, socket.SOCK_DGRAM)
            ips = {info[4][0] for info in infos}
            if len(ips) == 1:
                host = ips.pop()
        except OSError:
            pass
        options = [
            # Sans ``username``, l'appel sortant porte une autorité vide
            # — VoIP.ms répond REJECT « No authority found » (cause 50).
            ["username", self.voipms_username],
            ["secret", self.voipms_password],
        ]
        if self.caller_id:
            # VoIP.ms exige un DID du compte comme caller-ID sortant —
            # sinon REJECT « congestion » (cause 34).
            options.append(["callerid", '"%s" <%s>' % (self.caller_id, self.caller_id)])
        if client is not None:
            options.append(["context", self._resolve_incall_context(client)])
        return {
            # Un endpoint IAX par trunk : confd exige l'unicité du nom
            # globalement (tous tenants) — le nom du sous-compte VoIP.ms
            # est le seul libellé garanti unique par trunk. L'authentif-
            # ication entrante se fait par secret + host, pas par nom.
            "name": self.voipms_username,
            "type": "friend",
            "host": host,
            "options": options,
        }

    def _iax_register_payload(self, callback_exten=False):
        """Corps ``POST /registers/iax`` : l'enregistrement IAX sortant.

        L'entrant chevauche cet enregistrement — c'est tout l'intérêt
        d'IAX2 derrière le NAT. ``callback_context``/``callback_exten``
        disent où Asterisk dépose l'appel entrant : le contexte des
        incalls, à l'extension du DID routé (posée au routage).
        """
        body = {
            "auth_username": self.voipms_username,
            "auth_password": self.voipms_password,
            "remote_host": self.pop_host,
        }
        # Mesuré : tout callback casse le register IAX — « /exten »
        # (Unregistered sans tentative) comme « ?context » (getaddrinfo
        # sur la chaîne entière). Register nu : l'entrant passe par
        # l'endpoint, qui matche par IP et route par son contexte.
        del callback_exten
        return body

    def _voipms_client(self):
        return VoIPMSClient(self.env)

    def _ensure_voipms_subaccount(self):
        """Crée le sous-compte chez VoIP.ms si aucun identifiant n'est saisi.

        ``createSubAccount`` exige une longue liste de paramètres, mesurée
        en conditions réelles : sans ``protocol``, ``auth_type``,
        ``allowed_codecs``, ``dtmf_mode``, ``nat``, ``lock_international``,
        ``international_route`` et ``music_on_hold``, l'API refuse un par
        un (« Protocol was not provided », etc.). Le mot de passe est
        généré localement — le portail ne le rend jamais en retour — et
        stocké sur la fiche (champ limité au groupe gestionnaire).
        """
        if self.voipms_username and self.voipms_password:
            return
        import secrets

        sip_password = secrets.token_urlsafe(18)
        # Suffixe du sous-compte : mono-protocole chez VoIP.ms, deux
        # trunks distincts portent deux sous-comptes distincts.
        username = re.sub(r"[^a-z0-9]+", "", self.name.lower()) + (
            "iax" if self.protocol == "iax2" else ""
        )
        client = self._voipms_client()
        response = client._request(
            "createSubAccount",
            timeout=60,
            params={
                "username": username,
                # 1 = SIP, 3 = IAX2 (getProtocols) ; 1 = User/Password
                # (getAuthTypes) : le trunk Wazo s'authentifie par
                # identifiants, son IP est privée derrière le NAT.
                "protocol": 3 if self.protocol == "iax2" else 1,
                "auth_type": 1,
                "password": sip_password,
                "description": "Trunk Odoo %s" % self.name,
                "device_type": 1,  # 1 = IP PBX / passerelle (getDeviceTypes)
                "allowed_codecs": "ulaw;g729",
                "dtmf_mode": "rfc2833",
                "nat": "yes",
                "lock_international": 1,  # verrouillé : lever = geste explicite
                "international_route": 1,
                "music_on_hold": "default",
            },
        )
        # Réponse mesurée : {"status": "success", "id": …, "account":
        # "539175_diversecite"} — « account » est le nom d'utilisateur
        # COMPLET (numéro de compte principal + « _ » + nom donné).
        full_username = (response or {}).get("account")
        if not full_username:
            raise UserError(
                self.env._(
                    "VoIP.ms a créé le sous-compte sans rendre son nom "
                    "d'utilisateur : renseignez-le à la main depuis le portail."
                )
            )
        self.sudo().write({"voipms_username": full_username, "voipms_password": sip_password})

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_provision(self):
        """Provisionne le trunk côté VoIP.ms puis côté Wazo."""
        self.ensure_one()
        if self.state == "synced":
            raise UserError(self.env._("Le trunk %s est déjà provisionné.", self.name))
        # Identifiants distants relus AVANT le try : si l'échec survient
        # dès le sous-compte VoIP.ms, le bloc d'erreur doit pouvoir les
        # écrire sans UnboundLocalError — mesuré en conditions réelles.
        endpoint_uuid = self.remote_endpoint_uuid
        endpoint_iax_id = self.remote_endpoint_iax_id
        register_iax_id = self.remote_register_iax_id
        trunk_id = self.remote_trunk_id
        outcall_id = self.remote_outcall_id
        extension_id = self.remote_outcall_extension_id
        try:
            self._ensure_voipms_subaccount()
            client = self._wazo_client()
            if self.protocol == "iax2":
                # IAX2 : endpoint « friend » + register sortant —
                # l'entrant chevauchera le register (NAT sans port
                # ouvert). Chaque étape reprend l'id conservé.
                if not endpoint_iax_id:
                    endpoint_iax = client.conf(
                        "POST",
                        "/endpoints/iax",
                        body=self._iax_endpoint_payload(client),
                    )
                    endpoint_iax_id = endpoint_iax["id"]
                if not register_iax_id:
                    register_iax = client.conf(
                        "POST", "/registers/iax", body=self._iax_register_payload()
                    )
                    register_iax_id = register_iax["id"]
                if not trunk_id:
                    trunk = client.conf("POST", "/trunks", body={})
                    trunk_id = trunk["id"]
                client.conf("PUT", "/trunks/%s/endpoints/iax/%s" % (trunk_id, endpoint_iax_id))
                client.conf("PUT", "/trunks/%s/registers/iax/%s" % (trunk_id, register_iax_id))
            else:
                # SIP : endpoint trunk + registration sortante.
                if not endpoint_uuid:
                    endpoint = client.conf(
                        "POST", "/endpoints/sip", body=self._endpoint_payload(client)
                    )
                    endpoint_uuid = endpoint["uuid"]
                if not trunk_id:
                    trunk = client.conf("POST", "/trunks", body={})
                    trunk_id = trunk["id"]
                    client.conf("PUT", "/trunks/%s/endpoints/sip/%s" % (trunk_id, endpoint_uuid))
            # Extension (motif de sortie) d'abord : résolue ou créée à
            # la volée — le libellé « to-extern » ne désigne pas le
            # contexte dans les requêtes.
            if not extension_id:
                context_name = self._resolve_outcall_context(client)
                try:
                    extension = client.conf(
                        "POST",
                        "/extensions",
                        body={
                            "context": context_name,
                            "exten": "_%s." % self.outbound_prefix,
                        },
                    )
                except WazoAPIError as error:
                    # Deux trunks, même préfixe de sortie : le motif
                    # existe déjà — on le partage au lieu d'échouer
                    # (mesuré : « Extension already exists »).
                    if "already exists" not in str(error):
                        raise
                    response = client.conf(
                        "GET",
                        "/extensions",
                        params={
                            "context": context_name,
                            "exten": "_%s." % self.outbound_prefix,
                        },
                    )
                    items = response.get("items") or [] if isinstance(response, dict) else response
                    for item in items:
                        if item.get("exten") == "_%s." % self.outbound_prefix:
                            extension = item
                            break
                    else:
                        raise
                extension_id = extension["id"]
            # Outcall ensuite : réutilisé quand le motif partagé en a
            # déjà un (mesuré : extension<->outcall est 1:1 — un second
            # trunk de même préfixe reprend l'outcall existant, qui
            # accepte plusieurs trunks).
            if not outcall_id:
                outcall_id = self._resolve_outcall(client, extension_id)
            # Association systématique : elle exige un corps
            # OutcallExtension — sans lui, confd répond 400 (mesuré) — et
            # une reprise après échec ne doit pas la sauter. Le préfixe de
            # sortie est retiré du numéro avant l'envoi au trunk.
            # Si le motif appartient déjà à l'outcall réutilisé, confd
            # le refuse — c'est précisément le partage voulu.
            try:
                client.conf(
                    "PUT",
                    "/outcalls/%s/extensions/%s" % (outcall_id, extension_id),
                    body={"strip_digits": len(self.outbound_prefix)},
                )
            except WazoAPIError as error:
                if "is associated with a outcall" not in str(error):
                    raise
            # Schéma TrunksId : un dict « trunks », pas une liste nue —
            # mesuré : la liste seule fait répondre 400 « Invalid input
            # type ».
            client.conf(
                "PUT",
                "/outcalls/%s/trunks" % outcall_id,
                body={"trunks": [{"id": trunk_id}]},
            )
        except (WazoAPIError, VoIPMSAPIError, UserError) as error:
            # Tout ce qui a été créé à distance est conservé : la reprise
            # est idempotente, elle ne recrée rien — mesuré : perdre l'id
            # du trunk laissait un trunk orphelin côté Wazo, et la
            # relance échouait sur son association déjà existante.
            self.write(
                {
                    "state": "error",
                    "error_message": str(error),
                    "remote_endpoint_uuid": endpoint_uuid,
                    "remote_endpoint_iax_id": endpoint_iax_id,
                    "remote_register_iax_id": register_iax_id,
                    "remote_trunk_id": trunk_id,
                    "remote_outcall_id": outcall_id,
                    "remote_outcall_extension_id": extension_id,
                }
            )
            return False
        self.sudo().write(
            {
                "state": "synced",
                "remote_endpoint_uuid": endpoint_uuid,
                "remote_endpoint_iax_id": endpoint_iax_id,
                "remote_register_iax_id": register_iax_id,
                "remote_trunk_id": trunk_id,
                "remote_outcall_id": outcall_id,
                "remote_outcall_extension_id": extension_id,
                "error_message": False,
            }
        )
        return True

    @api.depends("protocol")
    def _compute_registered_label(self):
        for trunk in self:
            trunk.registered_label = trunk.protocol or "sip"

    def action_check_registration(self):
        """Lit l'état d'enregistrement : SIP côté VoIP.ms, IAX2 côté Wazo."""
        self.ensure_one()
        if self.protocol == "iax2":
            client = self._wazo_client()
            reponse = client._request(
                "confd", "GET", f"/registers/iax/{self.remote_register_iax_id}"
            )
            corps = (reponse or {}).get("json", reponse) or {}
            etat = corps.get("state") or corps.get("registered")
            actif = etat in ("registered", "yes", "True", True)
            self.sudo().write(
                {
                    "registered": bool(actif),
                    "error_message": "" if actif else f"IAX: {etat}",
                }
            )
            return True
        client = self._voipms_client()
        response = client._request("getRegistrationStatus", {"account": self.voipms_username})
        self.sudo().write({"registered": (response or {}).get("registered") == "yes"})
        return True

    def action_unprovision(self):
        """Retire les ressources Wazo (endpoint, trunk, outcall, motif).

        Le sous-compte VoIP.ms n'est **pas** supprimé : l'API ne le permet
        pas proprement et il peut servir ailleurs. Chaque étape tolère un
        404 pour rester idempotente.
        """
        self.ensure_one()
        client = self._wazo_client()

        def _ignore_404(method, path, **kwargs):
            try:
                client.conf(method, path, **kwargs)
            except WazoAPIError as error:
                if "HTTP 404" not in str(error):
                    raise
            return True

        try:
            if self.remote_outcall_id:
                _ignore_404(
                    "PUT",
                    "/outcalls/%s/trunks" % self.remote_outcall_id,
                    body={"trunks": []},
                )
                if self.remote_outcall_extension_id:
                    _ignore_404(
                        "DELETE",
                        "/outcalls/%s/extensions/%s"
                        % (self.remote_outcall_id, self.remote_outcall_extension_id),
                    )
                _ignore_404("DELETE", "/outcalls/%s" % self.remote_outcall_id)
            if self.remote_trunk_id and self.remote_endpoint_uuid:
                _ignore_404(
                    "DELETE",
                    "/trunks/%s/endpoints/sip/%s"
                    % (self.remote_trunk_id, self.remote_endpoint_uuid),
                )
            # IAX : les deux associations d'abord, le register avant
            # l'endpoint — l'entrant ne doit plus pointer vers rien.
            if self.remote_trunk_id and self.remote_endpoint_iax_id:
                _ignore_404(
                    "DELETE",
                    "/trunks/%s/endpoints/iax/%s"
                    % (self.remote_trunk_id, self.remote_endpoint_iax_id),
                )
            if self.remote_trunk_id and self.remote_register_iax_id:
                _ignore_404(
                    "DELETE",
                    "/trunks/%s/registers/iax/%s"
                    % (self.remote_trunk_id, self.remote_register_iax_id),
                )
            if self.remote_trunk_id:
                _ignore_404("DELETE", "/trunks/%s" % self.remote_trunk_id)
            if self.remote_endpoint_uuid:
                _ignore_404("DELETE", "/endpoints/sip/%s" % self.remote_endpoint_uuid)
            if self.remote_register_iax_id:
                _ignore_404("DELETE", "/registers/iax/%s" % self.remote_register_iax_id)
            if self.remote_endpoint_iax_id:
                _ignore_404("DELETE", "/endpoints/iax/%s" % self.remote_endpoint_iax_id)
        except WazoAPIError as error:
            self.write({"state": "error", "error_message": str(error)})
            return False
        self.sudo().write(
            {
                "state": "new",
                "remote_endpoint_uuid": False,
                "remote_endpoint_iax_id": False,
                "remote_register_iax_id": False,
                "remote_trunk_id": False,
                "remote_outcall_id": False,
                "remote_outcall_extension_id": False,
                "registered": False,
                "error_message": False,
            }
        )
        return True

    def action_retry(self):
        self.ensure_one()
        return self.action_provision()
