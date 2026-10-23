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
        help="Numéro présenté au RTC (E.164, ex. 14184803381). Doit être un "
        "DID du compte VoIP.ms.",
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
    remote_endpoint_uuid = fields.Char(string="UUID endpoint SIP Wazo")
    remote_trunk_id = fields.Integer(string="ID trunk Wazo")
    remote_outcall_id = fields.Integer(string="ID outcall Wazo")
    remote_outcall_extension_id = fields.Integer(string="ID motif outcall Wazo")
    registered = fields.Boolean(string="Enregistrement SIP actif", readonly=True)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint("unique(name)", "Ce nom de trunk existe déjà.")

    @api.constrains("outbound_prefix")
    def _check_outbound_prefix(self):
        for trunk in self:
            if trunk.outbound_prefix and not re.fullmatch(r"[0-9]+", trunk.outbound_prefix):
                raise ValidationError(
                    self.env._("Le préfixe de sortie doit être numérique.")
                )

    # ------------------------------------------------------------------
    # Côté Wazo
    # ------------------------------------------------------------------

    def _wazo_client(self):
        return self.env["wazo.user"]._wazo_client()

    def _wazo_tenant_uuid(self):
        return self.env["wazo.user"]._wazo_tenant_uuid()

    def _outcall_context(self):
        """Contexte des renvois sortants — ``to-extern`` sur Wazo 26."""
        return "to-extern"

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
                return item["name"]
        created = client.conf(
            "POST", "/contexts", body={"name": self._outcall_context(), "type": "outcall"}
        )
        return created["name"]

    def _endpoint_payload(self):
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
            "endpoint_section_options": [
                ["context", "from-extern"],
                ["from_user", self.caller_id or self.voipms_username],
            ],
        }

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
        username = re.sub(r"[^a-z0-9]+", "", self.name.lower())
        client = self._voipms_client()
        response = client._request(
            "createSubAccount",
            {
                "username": username,
                # 1 = SIP, 3 = IAX2 (getProtocols) ; 1 = User/Password
                # (getAuthTypes) : le trunk Wazo s'authentifie par
                # identifiants, son IP est privée derrière le NAT.
                "protocol": 1,
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
        self.sudo().write(
            {"voipms_username": full_username, "voipms_password": sip_password}
        )

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
        trunk_id = self.remote_trunk_id
        outcall_id = self.remote_outcall_id
        extension_id = self.remote_outcall_extension_id
        try:
            self._ensure_voipms_subaccount()
            client = self._wazo_client()
            # Endpoint SIP trunk (idempotent : on reprend l'uuid conservé).
            if not endpoint_uuid:
                endpoint = client.conf(
                    "POST", "/endpoints/sip", body=self._endpoint_payload()
                )
                endpoint_uuid = endpoint["uuid"]
            if not trunk_id:
                trunk = client.conf("POST", "/trunks", body={})
                trunk_id = trunk["id"]
                client.conf(
                    "PUT", "/trunks/%s/endpoints/sip/%s" % (trunk_id, endpoint_uuid)
                )
            # Outcall + motif de numérotation.
            if not outcall_id:
                # Reprise idempotente : un outcall orphelin d'une tentative
                # échouée est réutilisé par son nom, pas refusé (mesuré :
                # « Outcall already exists » sinon — l'outcall survit au
                # rollback Odoo, lui).
                try:
                    outcall = client.conf(
                        "POST", "/outcalls", body={"name": "out-%s" % self.name}
                    )
                except WazoAPIError as error:
                    if "already exists" not in str(error):
                        raise
                    response = client.conf("GET", "/outcalls")
                    items = (
                        response.get("items") or []
                        if isinstance(response, dict)
                        else []
                    )
                    for item in items:
                        if item.get("name") == "out-%s" % self.name:
                            outcall = item
                            break
                    else:
                        raise
                outcall_id = outcall["id"]
            if not extension_id:
                extension = client.conf(
                    "POST",
                    "/extensions",
                    body={
                        # Nom réel (généré par Wazo), résolu ou créé à la
                        # volée : le libellé « to-extern » ne désigne pas
                        # le contexte dans les requêtes.
                        "context": self._resolve_outcall_context(client),
                        "exten": "_%s." % self.outbound_prefix,
                    },
                )
                extension_id = extension["id"]
            # Association systématique (idempotente) : elle exige un corps
            # OutcallExtension — sans lui, confd répond 400 (mesuré) — et
            # une reprise après échec ne doit pas la sauter. Le préfixe de
            # sortie est retiré du numéro avant l'envoi au trunk.
            client.conf(
                "PUT",
                "/outcalls/%s/extensions/%s" % (outcall_id, extension_id),
                body={"strip_digits": len(self.outbound_prefix)},
            )
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
                "remote_trunk_id": trunk_id,
                "remote_outcall_id": outcall_id,
                "remote_outcall_extension_id": extension_id,
                "error_message": False,
            }
        )
        return True

    def action_check_registration(self):
        """Lit l'état de l'enregistrement SIP côté VoIP.ms."""
        self.ensure_one()
        client = self._voipms_client()
        response = client._request(
            "getRegistrationStatus", {"account": self.voipms_username}
        )
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
            if self.remote_trunk_id:
                _ignore_404("DELETE", "/trunks/%s" % self.remote_trunk_id)
            if self.remote_endpoint_uuid:
                _ignore_404(
                    "DELETE", "/endpoints/sip/%s" % self.remote_endpoint_uuid
                )
        except WazoAPIError as error:
            self.write({"state": "error", "error_message": str(error)})
            return False
        self.sudo().write(
            {
                "state": "new",
                "remote_endpoint_uuid": False,
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
