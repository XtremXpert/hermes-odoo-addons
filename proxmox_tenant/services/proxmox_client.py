# Part of the proxmox_tenant Odoo module. See LICENSE for details.
"""Client Proxmox VE — authentification par jeton API.

Proxmox accepte deux identites : le ticket (usager + mot de passe,
``/access/ticket``) et le jeton API ``user@realm!tokenid=uuid``, plus
leger et fait pour les integrations. On porte le jeton seul : il se
revoque cote Proxmox sans toucher au compte.

Reglages (parametres systeme) :

- ``proxmox.base_url`` — ``https://pve.exemple.com:8006`` ;
- ``proxmox.api_token`` — ``root@pam!odoo=xxxxxxxx-....`` ;
- ``proxmox.verify_ssl`` — ``0`` pour un certificat autosigne ;
- ``proxmox.allowed_pools`` — pools du tenant, separes par des virgules.
"""

import json
import ssl
import urllib.error
import urllib.request

from odoo import _
from odoo.exceptions import UserError

TIMEOUT_S = 20


class ProxmoxAPIError(Exception):
    """Le serveur Proxmox a refuse ou n'a pas repondu."""


class ProxmoxClient:
    """Le portier des appels a l'API Proxmox de l'instance."""

    def __init__(self, env, base_url=None, api_token=None, verify_ssl=None):
        icp = env["ir.config_parameter"].sudo()
        self.base_url = (base_url or icp.get_str("proxmox.base_url", "")).rstrip("/")
        self.api_token = api_token or icp.get_str("proxmox.api_token", "")
        if verify_ssl is None:
            verify_ssl = icp.get_str("proxmox.verify_ssl", "1") not in ("0", "", "false")
        self.verify_ssl = verify_ssl
        if not self.base_url or not self.api_token:
            raise UserError(
                _(
                    "Proxmox n'est pas configure : posez « proxmox.base_url » et "
                    "« proxmox.api_token » dans les parametres."
                )
            )

    def _request(self, method, path, data=None):
        """Un appel ``/api2/json`` ; renvoie la donnee ou leve ProxmoxAPIError."""
        url = "%s/api2/json%s" % (self.base_url, path)
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(url, data=body, method=method)
        request.headers["Authorization"] = "PVEAPIToken=%s" % self.api_token
        if body:
            request.headers["Content-Type"] = "application/json"
        contexte = None if self.verify_ssl else ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(request, context=contexte, timeout=TIMEOUT_S) as rep:
                charge = json.loads(rep.read() or b"{}")
        except urllib.error.HTTPError as erreur:
            raise ProxmoxAPIError(
                "Echec de l'appel a l'API Proxmox (HTTP %s, %s %s) : %s"
                % (erreur.code, method, path, erreur.reason)
            ) from erreur
        except OSError as erreur:
            raise ProxmoxAPIError(
                "Le serveur Proxmox ne repond pas (%s %s) : %s" % (method, path, erreur)
            ) from erreur
        return charge.get("data", charge)
