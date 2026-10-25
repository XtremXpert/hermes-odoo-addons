# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Client REST de la Wazo Platform (wazo.io).

Deux microservices sont utilisés :

* ``confd`` (``/api/confd/1.1``) : configuration — utilisateurs, lignes,
  postes (extensions), endpoints SIP, messageries vocales ;
* ``call-logd`` (``/api/call-logd/1.0``) : journal d'appels (CDR) ;
* ``auth`` (``/api/auth/0.1``) : comptes d'authentification SIP
  (nom d'utilisateur + mot de passe de registration).

L'authentification passe par l'en-tête ``X-Auth-Token`` (token API
généré dans Wazo) et le tenant éventuel par ``Wazo-Tenant``.

Note : les en-têtes sont passés directement à la construction de
``urllib.request.Request`` (et non via ``add_header``) afin de
préserver la casse exacte des en-têtes ``X-Auth-Token`` et
``Wazo-Tenant``.
"""

import base64
import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request

_logger = logging.getLogger(__name__)

TIMEOUT = 20.0

#: Taille de page pour la lecture des contextes.
_CONTEXT_PAGE = 100

#: Champs de ``GET /contexts/{id}`` portant les plages **déclarées**, par type
#: d'objet. Un seul appel rend donc tous les types d'un coup — d'où l'usage
#: pour le contrôle croisé (« ce numéro est-il réservé à un autre type ? »).
TYPE_RANGE_FIELDS = {
    "user": "user_ranges",
    "group": "group_ranges",
    "queue": "queue_ranges",
    "conference": "conference_room_ranges",
    "incall": "incall_ranges",
}


def in_ranges(number, items):
    """Le numéro tombe-t-il dans l'une des sous-plages données ?

    ``items`` est une liste rendue par :meth:`WazoClient.ranges`, chaque
    élément portant ``start`` et ``end``, bornes **incluses**.

    L'API rend ces bornes sous forme de **chaînes** (``"1000"``) : la
    comparaison se fait donc sur la valeur numérique — ``999`` précède
    ``1000``, ce qu'une comparaison textuelle inverse — sans jamais renoncer
    à la forme textuelle, qui repart ensuite vers l'API telle quelle.
    Un numéro non numérique ne lève pas : il ne correspond à rien.
    """
    try:
        valeur = int(str(number).strip())
    except (TypeError, ValueError):
        return False
    for item in items or ():
        try:
            debut = int(str(item.get("start")).strip())
            fin = int(str(item.get("end")).strip())
        except (TypeError, ValueError):
            continue
        if debut <= valeur <= fin:
            return True
    return False


class WazoAPIError(Exception):
    """Erreur de l'API Wazo (HTTP, réseau ou réponse illisible).

    ``status`` porte le code HTTP en cas d'erreur HTTP, ``None`` sinon
    (erreur réseau / réponse illisible). Permet au code appelant de
    distinguer un conflit (HTTP 409, ressource déjà existante) d'une
    autre erreur.
    """

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class WazoClient:
    def __init__(self, env, url=None, api_key=None, tenant_id=None):
        self.env = env
        # Résolution nom → id des contextes, valable le temps de l'instance.
        self._context_ids = {}
        icp = env["ir.config_parameter"].sudo()
        self.url = (
            (url if url is not None else icp.get_str("wazo.url", default="")).strip().rstrip("/")
        )
        if api_key is None:
            api_key = icp.get_str("wazo.api_key", default="")
        self.api_key = api_key or ""
        if tenant_id is None:
            tenant_id = icp.get_str("wazo.tenant_id", default="")
        self.tenant_id = tenant_id or ""
        # Un PBX interne porte souvent un certificat auto-signé (CN=localhost,
        # mesuré sur le nôtre) : la vérification TLS stricte d'urllib y échoue.
        # L'exception est explicite — paramètre « wazo.ssl_verify », défaut
        # « True » — jamais une tolérance cachée.
        self.ssl_verify = icp.get_str("wazo.ssl_verify", default="True").lower() not in {
            "false",
            "0",
            "no",
        }

    # -- Points d'entrée par microservice ----------------------------------

    def conf(self, method, path, params=None, body=None):
        """Requête vers wazo-confd (``/api/confd/1.1``)."""
        return self._request("confd", method, path, params=params, body=body)

    def call_logd(self, method, path, params=None, body=None, raw=False):
        """Requête vers wazo-call-logd (``/api/call-logd/1.0``)."""
        return self._request("call-logd", method, path, params=params, body=body, raw=raw)

    def auth(self, method, path, params=None, body=None):
        """Requête vers wazo-authd (``/api/auth/0.1``) — comptes SIP."""
        return self._request("auth", method, path, params=params, body=body)

    # -- Plages d'extensions (par contexte, donc par tenant) ----------------

    def context_id(self, name, refresh=False):
        """Identifiant **numérique** du contexte portant ``name``.

        Les endpoints et les extensions désignent leur contexte par son
        **nom**, alors que les plages s'adressent par **id** : cette
        résolution fait le pont. Retourne ``None`` si aucun contexte ne porte
        ce nom.

        La correspondance est mise en cache sur l'instance — elle ne change
        pas pendant une opération. ``refresh=True`` force la relecture.
        """
        name = (name or "").strip()
        if not name:
            return None
        if not refresh and name in self._context_ids:
            return self._context_ids[name]
        offset = 0
        while True:
            response = self.conf(
                "GET", "/contexts", params={"limit": _CONTEXT_PAGE, "offset": offset}
            )
            items = response.get("items") or [] if isinstance(response, dict) else response or []
            for item in items:
                if item.get("name") == name:
                    self._context_ids[name] = item.get("id")
                    return item.get("id")
            if len(items) < _CONTEXT_PAGE:
                return None
            offset += _CONTEXT_PAGE

    def ranges(self, context_name, range_type, availability="available"):
        """Sous-plages d'extensions déclarées pour un type, dans un contexte.

        ``range_type`` est un type de Wazo : ``user``, ``group``, ``queue``,
        ``conference``, ``incall``. ``availability`` vaut ``available``
        (sous-plages ne contenant que les numéros **libres**) ou ``all`` (la
        plage déclarée, pour tester une appartenance).

        Retourne une liste de ``{'start': int, 'end': int}``, vide si le
        contexte est inconnu ou si le type n'a **aucune** plage déclarée —
        cas normal : tous les types ne sont pas configurés côté Wazo.

        Le découpage de disponibilité est celui du PBX, qui considère toute
        extension existante comme indisponible, **même non attribuée** : ne
        jamais le recalculer soi-même.
        """
        context_id = self.context_id(context_name)
        if context_id is None:
            return []
        response = self.conf(
            "GET",
            "/contexts/%s/ranges/%s" % (context_id, range_type),
            params={"availability": availability},
        )
        return (response or {}).get("items") or []

    def declared_ranges(self, context_name):
        """Plages **déclarées** de tous les types d'un contexte, en un appel.

        Retourne ``{type: [{'start': '…', 'end': '…'}, …]}``, les clés étant
        celles de :data:`TYPE_RANGE_FIELDS` (``user``, ``group``, ``queue``,
        ``conference``, ``incall``). Un type sans plage déclarée rend une liste
        vide — cas normal, tous les types ne sont pas configurés.

        Sert au contrôle croisé : un numéro peut tomber dans la plage d'un
        **autre** type, et donc être refusé même s'il n'est encore utilisé par
        personne (réservation d'une plage pour des groupes à venir).

        Un contexte introuvable rend un dict aux listes vides. Les erreurs de
        l'API remontent : c'est à l'appelant de décider quoi faire d'un PBX
        muet, pas au client d'improviser.
        """
        vide = {type_: [] for type_ in TYPE_RANGE_FIELDS}
        context_id = self.context_id(context_name)
        if context_id is None:
            return vide
        response = self.conf("GET", "/contexts/%s" % context_id)
        if not isinstance(response, dict):
            return vide
        return {type_: response.get(field) or [] for type_, field in TYPE_RANGE_FIELDS.items()}

    # -- Internes ------------------------------------------------------------

    def _build_url(self, service, path, params=None):
        # Versions par microservice sur Wazo 26 :
        #   confd en 1.1, call-logd en 1.0, auth (authd) en 0.1.
        version = {
            "confd": "1.1",
            "call-logd": "1.0",
            "auth": "0.1",
        }.get(service, "1.0")
        url = "%s/api/%s/%s%s" % (self.url, service, version, path)
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return url

    def _request(self, service, method, path, params=None, body=None, basic=None, raw=False):
        """Appel HTTP à l'API Wazo.

        ``raw`` rend les octets tels quels — pour les téléchargements
        (enregistrements d'appels, sons) qui ne sont pas du JSON.

        ``basic`` est un couple ``(identifiant, mot de passe)`` : l'appel est
        alors authentifié en **Basic** et non par jeton, et l'en-tête
        ``Wazo-Tenant`` n'est pas envoyé — les identifiants désignent déjà le
        tenant, et un en-tête pourrait le contredire. C'est le cas de
        ``/token``, seul point d'entrée qui rend un jeton.
        """
        if not self.url or (not self.api_key and basic is None):
            raise WazoAPIError(
                "Connexion Wazo incomplète : renseignez l'URL du serveur et "
                "le token API dans Réglages > Applications > Téléphonie Wazo."
            )
        url = self._build_url(service, path, params)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if basic is not None:
            identifiant, mot_de_passe = basic
            secret = base64.b64encode(("%s:%s" % (identifiant, mot_de_passe)).encode("utf-8"))
            headers["Authorization"] = "Basic " + secret.decode("ascii")
        else:
            headers["X-Auth-Token"] = self.api_key
            if self.tenant_id:
                headers["Wazo-Tenant"] = self.tenant_id
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        # Contexte TLS : vérifié par défaut ; non vérifié seulement si
        # « wazo.ssl_verify » l'autorise explicitement (certificat
        # auto-signé du PBX interne).
        context = None
        if not self.ssl_verify:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT, context=context) as response:
                raw_bytes = response.read()
        except urllib.error.HTTPError as error:
            detail = ""
            try:
                detail = error.read().decode("utf-8", "replace")[:500]
            except (OSError, AttributeError):
                # Un corps d'erreur illisible ne doit pas masquer l'erreur.
                _logger.debug("Corps d'erreur Wazo illisible (%s %s)", method, path, exc_info=True)
            raise WazoAPIError(
                "Erreur de l"
                + "'API Wazo (%s %s) : HTTP %s. %s'" % (method, path, error.code, detail),
                status=error.code,
            ) from error
        except (urllib.error.URLError, OSError) as error:
            raise WazoAPIError(
                "Serveur Wazo injoignable sur %s (%s)." % (self.url, error)
            ) from error
        if raw:
            return raw_bytes
        if not raw_bytes:
            return None
        try:
            return json.loads(raw_bytes)
        except ValueError as error:
            raise WazoAPIError(
                "Réponse JSON illisible de l'API Wazo pour %s %s." % (method, path)
            ) from error

    def revoke_token(self, token):
        """Révoque un jeton (``DELETE /token/{jeton}``).

        La route de wazo-auth ne demande **aucune authentification** : celui qui
        connaît le jeton peut le tuer. C'est tout l'intérêt ici — reprendre un
        secret parti avec l'Odoo d'un client sans rien connaître d'autre, ni mot
        de passe d'administrateur ni jeton de service.

        Le jeton voyage dans le **chemin**, donc il se retrouve dans les
        journaux du serveur web : à l'appelant de ne pas le recopier dans ses
        propres traces.
        """
        return self._request("auth", "DELETE", "/token/%s" % token)

    def token(self, username, password, expiration=None, client_id=None):
        """Fabrique un jeton d'API pour un utilisateur (``POST /token``).

        Le point d'entrée est ``/token`` au **singulier** : ``/tokens``
        n'accepte que ``GET`` et répond 405 en écriture. L'authentification est
        en **Basic** (``username:password``) et non par jeton — c'est la seule
        façon d'obtenir un jeton, et le jeton administrateur n'a rien à faire
        dans cet appel.

        ``expiration`` est en secondes ; wazo-auth accepte jusqu'à dix ans
        (``315360000``), durée à préférer pour un jeton d'intégration, qui ne
        doit pas expirer comme une session de navigateur. ``client_id``
        rattache le jeton à un client, ce qui permet de le retrouver et de le
        révoquer sans le mot de passe.

        Rend la charge utile du jeton (``token``, ``expires_at``, ``acl``).
        """
        body = {}
        if expiration is not None:
            body["expiration"] = expiration
        if client_id:
            body["client_id"] = client_id
        response = self._request("auth", "POST", "/token", body=body, basic=(username, password))
        return (response or {}).get("data") or {}
