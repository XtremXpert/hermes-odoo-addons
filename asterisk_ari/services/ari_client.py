# Part of the asterisk_ari Odoo module. See LICENSE for details.
"""Client REST de l'API Asterisk ARI (Application Realtime Interface).

FreePBX expose ARI sur ``http://<hote>:8088/ari``. L'authentification est
HTTP Basic avec ``app_name:api_token``.

Endpoints utilisés (Milestone 1, REST uniquement — WebSocket en M2) :
- ``GET    /apps``          → liste les apps (test de connexion)
- ``GET    /calls``         → liste des appels actifs
- ``POST   /calls``         → origination (click-to-call)
- ``DELETE /calls/{id}``    → raccrocher
- ``POST   /calls/{id}/answer`` → répondre

Les paramètres supplémentaires passés à ``originate`` deviennent des
variables de dialplan (ex. ``target=5551234`` → ``${target}``).
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

from odoo.exceptions import UserError


class ARIError(UserError):
    """Erreur retournée par l'API ARI (HTTP non-2xx ou JSON invalide)."""


class ARIConfigError(UserError):
    """Configuration ARI absente (URL / app / token)."""


TIMEOUT = 30


class ARI:
    """Client REST ARI minimal pour le click-to-call et le suivi d'appels."""

    def __init__(self, env):
        self.env = env
        icp = env['ir.config_parameter'].sudo()
        self.base_url = icp.get_str('asterisk_ari.base_url', '').rstrip('/')
        self.app_name = icp.get_str('asterisk_ari.app_name', '')
        self.api_token = icp.get_str('asterisk_ari.api_token', '')

    def _check_config(self):
        if not self.base_url:
            raise ARIConfigError(
                "L'URL de base ARI n'est pas configurée "
                "(Réglages → Téléphonie).")
        if not self.app_name or not self.api_token:
            raise ARIConfigError(
                "L'application ARI ou le jeton ne sont pas configurés.")

    def _auth_header(self):
        raw = '%s:%s' % (self.app_name, self.api_token)
        token = base64.b64encode(raw.encode()).decode()
        return 'Basic ' + token

    def _request(self, method, path, params=None):
        """Appelle l'API ARI et retourne le JSON décodé.

        ``params`` est encodé en ``application/x-www-form-urlencoded``
        (POST/DELETE) ; pour GET les paramètres vont dans la query string.
        """
        self._check_config()
        url = self.base_url + path
        if method == 'GET' and params:
            url += '?' + urllib.parse.urlencode(params)
            data = None
        else:
            data = urllib.parse.urlencode(params).encode() if params else None

        req = urllib.request.Request(url, data=data, method=method)
        req.add_header('Authorization', self._auth_header())
        if data is not None:
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')

        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            try:
                detail = error.read().decode(errors='replace')
            except Exception:
                detail = str(error)
            raise ARIError('Erreur ARI %s : %s' % (error.code, detail)) from None
        except urllib.error.URLError as error:
            raise ARIError(
                'Impossible de joindre l\'API ARI : %s' % error.reason) from None

        if not body:
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError as error:
            raise ARIError('Réponse ARI invalide : %s' % body[:200]) from error

    # --- Actions ARI -----------------------------------------------------

    def list_apps(self):
        """``GET /apps`` — sert de test de connexion (auth + reachabilité)."""
        return self._request('GET', '/apps')

    def list_calls(self):
        """``GET /calls`` — liste des appels actifs."""
        result = self._request('GET', '/calls')
        return result if isinstance(result, list) else []

    def originate(self, endpoint, app=None, app_answered=False,
                  caller_id=None, **extra_vars):
        """``POST /calls`` — origination (click-to-call).

        ``extra_vars`` : variables de dialplan additionnelles (ex.
        ``target='5551234'``). Retourne l'objet Call ARI.
        """
        params = {'endpoint': endpoint, 'appAnswered': app_answered}
        if app:
            params['app'] = app
        if caller_id:
            params['callerId'] = caller_id
        params.update(extra_vars)
        return self._request('POST', '/calls', params)

    def answer(self, call_id):
        """``POST /calls/{id}/answer``."""
        return self._request('POST', '/calls/%s/answer' % call_id)

    def hangup(self, call_id):
        """``DELETE /calls/{id}``."""
        return self._request('DELETE', '/calls/%s' % call_id)