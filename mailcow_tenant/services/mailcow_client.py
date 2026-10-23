# Part of the mailcow_tenant Odoo module. See LICENSE for details.
"""Client minimal de l'API Mailcow v1 (urllib standard, sans dépendance externe)."""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import UTC
from datetime import datetime

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Délai d'un appel, comme le broker N3 : sans lui, un serveur muet bloque un
# processus Odoo indéfiniment.
DELAI = 30

# La clé API vient de l'environnement du conteneur quand il la fournit : un
# Secret Kubernetes copié depuis Vaultwarden, qui reste la source. Elle n'est
# alors ni dans la base, ni dans ses sauvegardes, ni dans un staging cloné.
VARIABLE_CLE = "MAILCOW_API_KEY"


def cle_de_l_environnement(env):
    """La clé fournie par l'environnement, sauf sur une base neutralisée.

    Un staging neutralisé ne doit jamais agir sur le vrai serveur, même si son
    conteneur reçoit la variable par erreur.
    """
    cle = os.environ.get(VARIABLE_CLE, "").strip()
    if not cle:
        return ""
    icp = env["ir.config_parameter"].sudo()
    if icp.get_str("database.is_neutralized", default=""):
        return ""
    return cle


RESULTAT_INCERTAIN = (
    "Résultat incertain (%s, %s %s) : la modification a pu être faite sur Mailcow. "
    "Synchronisez depuis Mailcow pour relire l'état avant de réessayer."
)


def en_nombre(valeur):
    """Mailcow envoie parfois les nombres sous forme de texte (« 25 »)."""
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return 0.0


def en_date(valeur):
    """Convertit un horodatage Unix de Mailcow en date Odoo.

    L'API renvoie les dernières connexions en secondes depuis 1970, et 0 pour
    « jamais ». Un affichage naïf casse : on convertit ici, une seule fois.
    """
    if isinstance(valeur, (int, float)) and valeur:
        return datetime.fromtimestamp(float(valeur), UTC).replace(tzinfo=None)
    return False


def refuser_la_disparition_totale(env, entries, modele, etiquette):
    """Refuse de conclure à la disparition totale sur un listage vide.

    Mailcow peut répondre « rien » sur une panne passagère. Conclure que tout a
    disparu du serveur marquerait chaque fiche « non synchronisée » en silence :
    un état faux, et c'est dans ces moments-là qu'on agit mal.
    """
    if entries:
        return
    # Seules les fiches crues présentes sur le serveur comptent : une fiche
    # jamais poussée n'a rien à voir avec un serveur qui répond « rien ».
    locales = env[modele].search_count([("synced", "=", True)])
    if locales:
        raise MailcowAPIError(
            "Mailcow n'a renvoyé aucune %s alors que %d fiche(s) locale(s) "
            "existent. Rien n'a été marqué comme disparu : vérifiez d'abord la "
            "connexion au serveur." % (etiquette, locales)
        )


class MailcowAPIError(UserError):
    """Erreur lors d'un appel à l'API Mailcow."""


class MailcowClient:
    """Client de l'API Mailcow v1.

    L'URL vient de ``ir.config_parameter`` (``mailcow.base_url``). La clé vient
    de la variable d'environnement ``MAILCOW_API_KEY`` si elle est fournie, sinon
    du paramètre ``mailcow.api_key``.
    """

    def __init__(self, env, base_url=None, api_key=None):
        self.env = env
        # Les réglages du module sont administrés par l'administrateur, mais ils
        # sont lus POUR l'utilisateur qui agit : sans sudo, un gestionnaire se
        # voit refuser l'aperçu comme la synchronisation (« You are not allowed
        # to access 'System Parameter' »). La clé ne sort jamais d'ici : elle
        # part dans l'en-tête de la requête, jamais dans une erreur.
        icp = env["ir.config_parameter"].sudo()
        self.base_url = base_url or icp.get_str("mailcow.base_url", default="")
        self.api_key = (
            api_key or cle_de_l_environnement(env) or icp.get_str("mailcow.api_key", default="")
        )

    def _request(self, method, path, payload=None):
        """Appelle l'API et renvoie la liste ``data`` de la réponse Mailcow."""
        if not self.base_url or not self.api_key:
            raise MailcowAPIError(
                "Le serveur Mailcow n'est pas configuré. Renseignez l'URL de base "
                "(paramètre « mailcow.base_url ») et la clé API (variable "
                "d'environnement MAILCOW_API_KEY, ou paramètre « mailcow.api_key ») "
                "dans Réglages > Mailcow."
            )
        url = self.base_url.rstrip("/") + "/api/v1" + path
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method.upper(),
        )
        # Conservation du nom d'en-tête exact attendu par Mailcow :
        # Request.add_header() capitalise les noms (X-api-key), ce qui
        # casserait une recherche sensible à la casse.
        request.headers["X-API-Key"] = self.api_key
        # Seule une lecture se reprend. Une écriture a pu aboutir sur le serveur
        # avant l'erreur reçue : la rejouer créerait ou supprimerait deux fois.
        lecture = method.upper() == "GET"
        tentatives = (1, 2, 3) if lecture else (1,)
        for tentative in tentatives:
            try:
                with urllib.request.urlopen(request, timeout=DELAI) as response:
                    body = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as error:
                # 429 et les 5xx sont passagers : on reprend avant d'abandonner.
                passager = error.code in (429, 500, 502, 503, 504)
                if passager and tentative < tentatives[-1]:
                    time.sleep(tentative)
                    continue
                if passager and not lecture:
                    raise MailcowAPIError(
                        RESULTAT_INCERTAIN % ("HTTP %d" % error.code, method.upper(), path)
                    ) from error
                raise MailcowAPIError(
                    "Échec de l'appel à l'API Mailcow (HTTP %d, %s %s) : %s"
                    % (error.code, method.upper(), path, error.reason)
                ) from error
            except (urllib.error.URLError, TimeoutError) as error:
                if tentative < tentatives[-1]:
                    time.sleep(tentative)
                    continue
                if not lecture:
                    raise MailcowAPIError(
                        RESULTAT_INCERTAIN
                        % (getattr(error, "reason", None) or error, method.upper(), path)
                    ) from error
                raise MailcowAPIError(
                    "Serveur Mailcow inaccessible (%s) : %s"
                    % (url, getattr(error, "reason", None) or error)
                ) from error
        try:
            result = json.loads(body)
        except json.JSONDecodeError as error:
            raise MailcowAPIError("Réponse illisible de l'API Mailcow pour %s." % path) from error
        if result is None:
            return []
        entries = result.get("data") if isinstance(result, dict) and "data" in result else result
        if entries is None:
            raise MailcowAPIError("Réponse inattendue de Mailcow pour %s." % path)
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            raise MailcowAPIError("Réponse inattendue de Mailcow pour %s." % path)
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") in ("danger", "error"):
                raise MailcowAPIError(entry.get("msg") or "Erreur Mailcow non détaillée.")
            if entry.get("msg"):
                self._notify(entry)
        return entries

    @staticmethod
    def _texte_lisible(message):
        """Rend lisible le message d'une réponse Mailcow.

        Mailcow renvoie souvent une clé de traduction et ses arguments
        (["domain_added", "exemple.com"]) plutôt qu'une phrase. Publiée telle
        quelle, la liste afficherait du JSON dans le bandeau.
        """
        if isinstance(message, (list, tuple)):
            return " ".join(str(mot).replace("_", " ") for mot in message)
        if isinstance(message, dict):
            return " ".join(str(valeur) for valeur in message.values())
        return str(message)

    def _notify(self, entry):
        """Pousse une notification dans le client Odoo (best effort).

        ``_bus_send`` et non ``_sendone`` : le bus d'Odoo recommande la
        première, qui vise la connexion de l'utilisateur. Publier sur un canal
        nommé à la main ne mène nulle part — rien dans ce module ne l'écoute —
        et le nom d'un tel canal doit être imprévisible, ce que « mailcow »
        n'est pas. Le type ``simple_notification`` est celui que le service
        natif du bus affiche.
        """
        try:
            self.env.user._bus_send(
                "simple_notification",
                {
                    "type": "success" if entry.get("type") == "success" else "info",
                    "title": "Mailcow",
                    "message": self._texte_lisible(entry["msg"]),
                    "sticky": True,
                },
            )
        except Exception:
            _logger.debug("Notification Mailcow non envoyée", exc_info=True)
