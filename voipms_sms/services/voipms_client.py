# Part of the voipms_sms Odoo module. See LICENSE for details.
"""Client REST v1 de l'API VoIP.ms (https://voip.ms/api/v1/rest.php).

L'authentification passe par les paramètres ``api_username`` et
``api_password`` (qui porte la valeur du Token du portail, pas le
password SIP). Les paramètres de méthode sont encodés dans l'URL
(requête GET) ; aucune clé dans les headers.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://voip.ms/api/v1/rest.php"
TIMEOUT = 20.0


class VoIPMSAPIError(Exception):
    """Erreur de l'API VoIP.ms (statut != success ou échec réseau)."""


class VoIPMSClient:
    def __init__(self, env, username=None, token=None):
        self.env = env
        icp = env["ir.config_parameter"].sudo()
        self.username = username or icp.get_str("voipms.api_username", default="")
        self.token = token or icp.get_str("voipms.api_token", default="")

    def _request(self, method, params=None):
        if not self.username or not self.token:
            raise VoIPMSAPIError("Identifiants VoIP.ms manquants (réglages > VoIP.ms SMS).")
        payload = {"api_username": self.username, "api_password": self.token, "method": method}
        if params:
            payload.update(params)
        url = API_URL + "?" + urllib.parse.urlencode(payload)
        try:
            # VoIP.ms rejects Python's default urllib User-Agent with 403.
            request = urllib.request.Request(
                url, headers={"User-Agent": "voipms_sms/1.0 (Odoo)"}
            )
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                body = response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as error:
            # Jamais d'URL dans le message : les identifiants y figurent.
            raise VoIPMSAPIError("Échec de la requête vers l'API VoIP.ms.") from error
        try:
            data = json.loads(body)
        except (ValueError, AttributeError) as error:
            raise VoIPMSAPIError("Réponse illisible de l'API VoIP.ms.") from error
        if str(data.get("status")) != "success":
            raise VoIPMSAPIError(
                "VoIP.ms a rejeté la requête %s : %s"
                % (method, data.get("message") or data.get("status"))
            )
        return data
