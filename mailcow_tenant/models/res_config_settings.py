# Part of the mailcow_tenant Odoo module. See LICENSE for details.
from odoo import fields
from odoo import models

from ..services.mailcow_client import MailcowClient
from ..services.mailcow_client import cle_de_l_environnement


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mailcow_base_url = fields.Char(
        string="URL du serveur Mailcow",
        config_parameter="mailcow.base_url",
        help="URL de base du serveur Mailcow, sans /api/v1 (ex. https://mail.diverse-cite.com).",
    )
    mailcow_api_key = fields.Char(
        string="Clé API Mailcow",
        config_parameter="mailcow.api_key",
        help="Clé API créée dans l'interface d'administration de Mailcow "
        "(section API, en bas de l'écran d'accueil).",
    )

    mailcow_api_key_from_env = fields.Boolean(
        string="Clé API fournie par l'environnement",
        compute="_compute_mailcow_api_key_from_env",
        help="La variable MAILCOW_API_KEY du conteneur fournit la clé : le champ "
        "Clé API Mailcow est alors ignoré.",
    )

    def _compute_mailcow_api_key_from_env(self):
        fournie = bool(cle_de_l_environnement(self.env))
        for reglages in self:
            reglages.mailcow_api_key_from_env = fournie

    def action_test_mailcow_connection(self):
        """Teste la connexion en listant les domaines du serveur.

        La route de listage est « /get/domain/all » : « /get/domain/111 » répond
        200 avec un corps vide, ce qui ferait passer un échec pour un succès.
        """
        client = MailcowClient(self.env)
        # La version d'abord : elle se lit sur une route qui répond toujours,
        # et savoir quel serveur on pilote évite bien des suppositions.
        try:
            version = client._request("GET", "/get/status/version")
        except Exception:  # noqa: BLE001 — la version n'est pas vitale
            version = None
        if isinstance(version, list) and version and isinstance(version[0], dict):
            version = version[0].get("version")
        elif not isinstance(version, str):
            version = None

        response = client._request("GET", "/get/domain/all")
        entries = response.get("data") if isinstance(response, dict) else response
        count = len([e for e in entries if isinstance(e, dict)])
        if not count:
            # Aucun domaine : la connexion a abouti mais l'API ne renvoie rien.
            # L'annoncer comme un succès tromperait l'utilisateur.
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Mailcow",
                    "message": (
                        "Connexion à Mailcow établie, mais le serveur ne renvoie "
                        "aucun domaine. Vérifiez les droits de la clé API."
                    ),
                    "type": "warning",
                    "sticky": True,
                },
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Mailcow",
                "message": (
                    "Connexion à Mailcow réussie : %d domaine(s) trouvé(s)"
                    "%s." % (count, " — serveur %s" % version if version else "")
                ),
                "type": "success",
                "sticky": False,
            },
        }
