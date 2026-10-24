# Part of the wazo_voipms Odoo module. See LICENSE for details.
"""Routage entrant d'un DID VoIP.ms vers une destination Wazo.

Le pont a deux moitiés, chacune idempotente :

* **Wazo** — un ``incall`` dans le contexte ``from-extern`` : le numéro
  composé est associé à une destination (utilisateur ou groupe d'appel) ;
* **VoIP.ms** — ``setDIDRouting`` bascule le DID en routage ``sip:`` vers
  ``sip:<numéro>@<hôte Wazo public>`` : l'appel entrant arrive en SIP sur
  le trunk et déclenche l'incall.

La destination Wazo est un choix entre ``wazo.user`` et
``wazo.ring.group`` — un seul des deux champs est requis, validé par
contrainte : Wazo n'accepte qu'une destination par incall.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSAPIError
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient
from odoo.addons.wazo_tenant.services.wazo_client import WazoAPIError
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError


class VoIPMSDid(models.Model):
    _inherit = "voipms.did"

    wazo_destination_type = fields.Selection(
        selection=[
            ("none", "Aucune"),
            ("user", "Utilisateur Wazo"),
            ("group", "Groupe d'appel"),
            ("queue", "File d'attente"),
            ("ivr", "Menu vocal (IVR)"),
            ("conference", "Salle de conférence"),
            ("voicemail", "Messagerie vocale"),
        ],
        string="Destination Wazo",
        default="none",
    )
    wazo_user_id = fields.Many2one("wazo.user", string="Utilisateur Wazo")
    trunk_id = fields.Many2one(
        "wazo.voipms.trunk",
        string="Trunk porteur de l'entrant",
        help="Trunk VoIP.ms par lequel les appels entrants arrivent. "
        "Un trunk IAX2 les fait cheminer par son enregistrement IAX — "
        "aucun port à exposer. Un trunk SIP exige que le Wazo soit "
        "joignable publiquement (URI sip:).",
    )
    wazo_ring_group_id = fields.Many2one(
        "wazo.ring.group", string="Groupe d'appel"
    )
    wazo_queue_id = fields.Many2one("wazo.queue", string="File d'attente")
    wazo_ivr_id = fields.Many2one("wazo.ivr", string="Menu vocal")
    wazo_conference_id = fields.Many2one("wazo.conference", string="Conférence")
    wazo_voicemail_id = fields.Many2one("wazo.voicemail", string="Messagerie vocale")
    wazo_incall_id = fields.Integer(string="ID incall Wazo", readonly=True)
    wazo_incall_extension_id = fields.Integer(
        string="ID extension incall", readonly=True
    )
    wazo_route_state = fields.Selection(
        selection=[
            ("none", "Non routé"),
            ("routed", "Routé vers Wazo"),
            ("error", "Erreur"),
        ],
        string="Routage",
        default="none",
        required=True,
        readonly=True,
    )
    wazo_route_error = fields.Text(string="Erreur de routage", readonly=True)

    # ------------------------------------------------------------------
    # Validation et résolution de la destination
    # ------------------------------------------------------------------

    @api.constrains(
        "wazo_destination_type",
        "wazo_user_id",
        "wazo_ring_group_id",
        "wazo_queue_id",
        "wazo_ivr_id",
        "wazo_conference_id",
        "wazo_voicemail_id",
    )
    def _check_wazo_destination(self):
        #: (clé du type, champ m2o) — un seul requis par type choisi.
        attendus = {
            "user": "wazo_user_id",
            "group": "wazo_ring_group_id",
            "queue": "wazo_queue_id",
            "ivr": "wazo_ivr_id",
            "conference": "wazo_conference_id",
            "voicemail": "wazo_voicemail_id",
        }
        for did in self:
            champ = attendus.get(did.wazo_destination_type)
            if champ and not did[champ]:
                raise ValidationError(
                    self.env._(
                        "Choisissez la destination Wazo du routage (%s).",
                        did.wazo_destination_type,
                    )
                )

    def _wazo_client(self):
        return self.env["wazo.user"]._wazo_client()

    def _wazo_public_host(self):
        """Hôte public du serveur Wazo, pour l'URI SIP du routage VoIP.ms."""
        url = (
            self.env["ir.config_parameter"].sudo().get_str("wazo.url", default="")
        ).strip()
        if not url:
            raise UserError(
                self.env._("Configurez l'URL du serveur Wazo avant le routage.")
            )
        return url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]

    def _destination_payload(self):
        """Corps ``destination`` de l'incall, selon le type choisi."""
        self.ensure_one()
        if self.wazo_destination_type == "user":
            if self.wazo_user_id.wazo_state != "synced":
                raise UserError(
                    self.env._(
                        "L'utilisateur %s n'est pas synchronisé sur Wazo.",
                        self.wazo_user_id.name,
                    )
                )
            return {"type": "user", "user_id": int(self.wazo_user_id.remote_user_id)}
        if self.wazo_destination_type == "group":
            if self.wazo_ring_group_id.wazo_state != "synced":
                raise UserError(
                    self.env._(
                        "Le groupe %s n'est pas synchronisé sur Wazo.",
                        self.wazo_ring_group_id.name,
                    )
                )
            return {
                "type": "group",
                # Mesuré : confd exige l'id NUMÉRIQUE du groupe pour un
                # incall — l'UUID est refusé (« Not a valid integer »).
                "group_id": self.wazo_ring_group_id.remote_group_numeric_id,
            }
        # Destinations objets : chaque id distant, avec le refus net si
        # la cible n'est pas synchronisée.
        pour_objet = {
            "queue": (self.wazo_queue_id, "remote_queue_id", "queue_id"),
            "ivr": (self.wazo_ivr_id, "remote_ivr_id", "ivr_id"),
            "conference": (self.wazo_conference_id, "remote_conference_id", "conference_id"),
            "voicemail": (self.wazo_voicemail_id, "remote_voicemail_id", "voicemail_id"),
        }
        cible = pour_objet.get(self.wazo_destination_type)
        if cible:
            objet, champ_id, cle_corps = cible
            if objet.wazo_state != "synced":
                raise UserError(
                    self.env._(
                        "%s n'est pas synchronisé sur Wazo.", objet.name
                    )
                )
            return {"type": self.wazo_destination_type, cle_corps: objet[champ_id]}
        return {"type": "none"}

    def _sip_routing_uri(self):
        """URI SIP que VoIP.ms appellera : ``sip:<DID>@<hôte Wazo>``."""
        return "sip:%s@%s" % (self.number, self._wazo_public_host())

    def _resolve_incall_context(self, client):
        """Nom du contexte des renvois entrants, créé au besoin.

        Mesuré sur un Wazo neuf : « from-extern » n'existe pas — et un
        poste d'incall exige un contexte de type « incall ». Wazo 26
        génère un nom interne : l'extension désigne ce nom, pas le
        libellé.
        """
        response = client.conf("GET", "/contexts")
        items = response.get("items") or [] if isinstance(response, dict) else []
        for item in items:
            if item.get("label") == "from-extern":
                return item["name"]
        created = client.conf(
            "POST", "/contexts", body={"label": "from-extern", "type": "incall"}
        )
        return created["name"]

    def _voipms_did_number(self):
        """Le DID côté VoIP.ms : sans l'indicatif pays NANP.

        La fiche porte le numéro normalisé E.164 (« 1418… ») mais
        l'API le refuse tel quel (mesuré : « This is not a valid DID ») —
        elle veut les dix chiffres locaux.
        """
        number = (self.number or "").strip()
        if len(number) == 11 and number.startswith("1"):
            return number[1:]
        return number

    def _routing_value(self):
        """Routage VoIP.ms du DID : ``sip:`` ou ``account:``.

        Avec un trunk choisi, le routage cible son sous-compte : l'appel
        entre par l'enregistrement du Wazo chez VoIP.ms — SIP ou IAX2,
        c'est l'enregistrement qui porte l'entrant (mesuré : le DID vise
        le sous-compte, l'appel suit son protocole). Sans trunk, l'URI
        sip: exige un hôte public.
        """
        if self.trunk_id:
            if self.trunk_id.state != "synced":
                raise UserError(
                    self.env._(
                        "Provisionnez d'abord le trunk %s.", self.trunk_id.name
                    )
                )
            return "account:%s" % self.trunk_id.voipms_username
        return self._sip_routing_uri()

    def _update_iax_callback(self, client):
        """Pointe le callback du register IAX vers l'incall du DID.

        L'appel entrant débarque dans ``from-extern`` à l'extension du
        DID : c'est ce que ``callback_extension`` règle sur le register.
        """
        if not self.trunk_id or self.trunk_id.protocol != "iax2":
            return
        body = self.trunk_id._iax_register_payload(
            callback_exten=self._voipms_did_number()
        )
        client.conf(
            "PUT",
            "/registers/iax/%s" % self.trunk_id.remote_register_iax_id,
            body=body,
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_route_to_wazo(self):
        """Crée l'incall Wazo puis bascule le routage VoIP.ms en sip:.

        L'ordre est choisi pour ne jamais laisser le DID sans destination :
        le routage VoIP.ms n'est basculé qu'une fois l'incall en place.
        """
        self.ensure_one()
        if self.wazo_route_state == "routed":
            raise UserError(
                self.env._("Le DID %s est déjà routé vers Wazo.", self.number)
            )
        incall_id = self.wazo_incall_id or False
        incall_extension_id = self.wazo_incall_extension_id or False
        try:
            client = self._wazo_client()
            # Incall : créé si absent, destination ré-appliquée sinon.
            if self.wazo_incall_id:
                client.conf(
                    "PUT",
                    "/incalls/%s" % self.wazo_incall_id,
                    body={"destination": self._destination_payload()},
                )
                incall_id = self.wazo_incall_id
                incall_extension_id = self.wazo_incall_extension_id
            else:
                incall = client.conf(
                    "POST",
                    "/incalls",
                    body={
                        "destination": self._destination_payload(),
                    },
                )
                incall_id = incall["id"]
                incall_extension_id = False
            # Le poste du renvoi : créé PUIS associé, quel que soit le
            # chemin — mesuré, les extensions embarquées du POST
            # /incalls sont ignorées, et une reprise sans poste est un
            # renvoi muet.
            if not incall_extension_id:
                incall_context = self._resolve_incall_context(client)
                try:
                    # Mesuré : l'INVITE de VoIP.ms porte le DID à dix
                    # chiffres — l'extension de l'incall prend la forme
                    # locale, l'E.164 ne matche jamais.
                    extension = client.conf(
                        "POST",
                        "/extensions",
                        body={
                            "exten": self._voipms_did_number(),
                            "context": incall_context,
                        },
                    )
                except WazoAPIError as error:
                    # Reprise d'orphelin : le poste survit au rollback.
                    if "already exists" not in str(error):
                        raise
                    response = client.conf(
                        "GET",
                        "/extensions",
                        params={
                            "exten": self._voipms_did_number(),
                            "context": incall_context,
                        },
                    )
                    items = (
                        response.get("items") or []
                        if isinstance(response, dict)
                        else response
                    )
                    for item in items:
                        if str(item.get("exten")) == str(self.number):
                            extension = item
                            break
                    else:
                        raise
                incall_extension_id = extension["id"]
                client.conf(
                    "PUT",
                    "/incalls/%s/extensions/%s" % (incall_id, incall_extension_id),
                )
            # Plus de callback sur le register IAX : tout callback casse
            # l'objet (mesuré). L'entrant route par l'endpoint du trunk
            # — IP du POP + contexte incall + extension livrée.
            # Bascule VoIP.ms : account: (trunk IAX) ou sip:<DID>@<hôte>.
            response = self._voipms_client()._request(
                "setDIDRouting",
                {"did": self._voipms_did_number(), "routing": self._routing_value()},
            )
            if str(response.get("status")) != "success":
                raise UserError(
                    self.env._("VoIP.ms a refusé le routage : %s") % response
                )
        except (WazoAPIError, VoIPMSAPIError, UserError) as error:
            self.sudo().write(
                {
                    "wazo_route_state": "error",
                    "wazo_route_error": str(error),
                    "wazo_incall_id": incall_id,
                }
            )
            return False
        self.sudo().write(
            {
                "wazo_route_state": "routed",
                "wazo_incall_id": incall_id,
                "wazo_incall_extension_id": incall_extension_id or False,
                "wazo_route_error": False,
            }
        )
        return True

    def action_unroute_from_wazo(self):
        """Retire l'incall Wazo et remet le DID en routage hangup.

        Le routage VoIP.ms est d'abord basculé vers ``sys:hangup`` : la
        suppression de l'incall ensuite ne laisse jamais un routage vers
        un Wazo sans destination.
        """
        self.ensure_one()
        client = self._wazo_client()
        try:
            # 1. Retirer le routage VoIP.ms, et d'abord le callback
            # IAX : l'entrant ne doit plus tomber dans from-extern sur
            # un poste qui n'a plus d'incall.
            if self.trunk_id and self.trunk_id.protocol == "iax2":
                body = self.trunk_id._iax_register_payload()
                client.conf(
                    "PUT",
                    "/registers/iax/%s" % self.trunk_id.remote_register_iax_id,
                    body=body,
                )
            self._voipms_client()._request(
                "setDIDRouting",
                {"did": self._voipms_did_number(), "routing": "sys:hangup"},
            )
            # 2. Supprimer l'incall (dissocier l'extension d'abord si présente).
            if self.wazo_incall_id and self.wazo_incall_extension_id:
                try:
                    client.conf(
                        "DELETE",
                        "/incalls/%s/extensions/%s"
                        % (self.wazo_incall_id, self.wazo_incall_extension_id),
                    )
                except WazoAPIError as error:
                    if "HTTP 404" not in str(error):
                        raise
            if self.wazo_incall_id:
                try:
                    client.conf("DELETE", "/incalls/%s" % self.wazo_incall_id)
                except WazoAPIError as error:
                    if "HTTP 404" not in str(error):
                        raise
            # 3. L'extension « from-extern » devient orpheline : on la retire.
            if self.wazo_incall_extension_id:
                try:
                    client.conf(
                        "DELETE", "/extensions/%s" % self.wazo_incall_extension_id
                    )
                except WazoAPIError as error:
                    if "HTTP 404" not in str(error):
                        raise
        except (WazoAPIError, VoIPMSAPIError) as error:
            self.sudo().write(
                {"wazo_route_state": "error", "wazo_route_error": str(error)}
            )
            return False
        self.sudo().write(
            {
                "wazo_route_state": "none",
                "wazo_incall_id": False,
                "wazo_incall_extension_id": False,
                "wazo_route_error": False,
            }
        )
        return True

    def _voipms_client(self):
        return VoIPMSClient(self.env)
