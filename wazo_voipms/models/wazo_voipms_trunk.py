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
            "registration_section_options": [
                ["client_uri", "sip:%s@%s" % (self.voipms_username, self.pop_host)],
                ["server_uri", "sip:%s" % self.pop_host],
                ["retry_interval", "60"],
                ["expiration", "120"],
                ["outbound_proxy", "sip:%s" % self.pop_host],
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

        ``createSubAccount`` rend un mot de passe généré par le portail ;
        il est stocké sur la fiche (champ limité au groupe gestionnaire).
        """
        if self.voipms_username and self.voipms_password:
            return
        client = self._voipms_client()
        response = client._request(
            "createSubAccount",
            {"username": self.name, "description": "Trunk Odoo %s" % self.name},
        )
        account = (response or {}).get("account") or {}
        username = account.get("username") or (response or {}).get("username")
        password = account.get("password") or (response or {}).get("password")
        if not username or not password:
            raise UserError(
                self.env._(
                    "VoIP.ms a créé le sous-compte sans rendre ses identifiants SIP : "
                    "renseignez-les à la main depuis le portail."
                )
            )
        self.sudo().write({"voipms_username": username, "voipms_password": password})

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_provision(self):
        """Provisionne le trunk côté VoIP.ms puis côté Wazo."""
        self.ensure_one()
        if self.state == "synced":
            raise UserError(self.env._("Le trunk %s est déjà provisionné.", self.name))
        try:
            self._ensure_voipms_subaccount()
            client = self._wazo_client()
            # Endpoint SIP trunk (idempotent : on reprend l'uuid conservé).
            endpoint_uuid = self.remote_endpoint_uuid
            if not endpoint_uuid:
                endpoint = client.conf(
                    "POST", "/endpoints/sip", body=self._endpoint_payload()
                )
                endpoint_uuid = endpoint["uuid"]
            # Trunk + association endpoint.
            trunk_id = self.remote_trunk_id
            if not trunk_id:
                trunk = client.conf("POST", "/trunks", body={})
                trunk_id = trunk["id"]
                client.conf(
                    "PUT", "/trunks/%s/endpoints/sip/%s" % (trunk_id, endpoint_uuid)
                )
            # Outcall + motif de numérotation.
            outcall_id = self.remote_outcall_id
            if not outcall_id:
                outcall = client.conf(
                    "POST", "/outcalls", body={"name": "out-%s" % self.name}
                )
                outcall_id = outcall["id"]
            extension_id = self.remote_outcall_extension_id
            if not extension_id:
                extension = client.conf(
                    "POST",
                    "/extensions",
                    body={
                        "context": self._outcall_context(),
                        "exten": "_%s." % self.outbound_prefix,
                    },
                )
                extension_id = extension["id"]
                client.conf(
                    "PUT", "/outcalls/%s/extensions/%s" % (outcall_id, extension_id)
                )
            client.conf(
                "PUT", "/outcalls/%s/trunks" % outcall_id, body=[{"id": trunk_id}]
            )
        except (WazoAPIError, VoIPMSAPIError, UserError) as error:
            self.write(
                {
                    "state": "error",
                    "error_message": str(error),
                    "remote_endpoint_uuid": endpoint_uuid or self.remote_endpoint_uuid,
                    "remote_trunk_id": self.remote_trunk_id,
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
                    "PUT", "/outcalls/%s/trunks" % self.remote_outcall_id, body=[]
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
