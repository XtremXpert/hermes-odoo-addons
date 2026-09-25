# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Client minimal de l'API Mailcow v1 (urllib standard, sans dépendance externe)."""

from datetime import datetime, timezone

import json
import time
import urllib.error
import urllib.request

from odoo.exceptions import UserError


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
        return datetime.fromtimestamp(float(valeur), timezone.utc).replace(tzinfo=None)
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
    locales = env[modele].search_count([('synced', '=', True)])
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

    Lecture de la configuration depuis ``ir.config_parameter``
    (``mailcow.base_url``, ``mailcow.api_key``), avec surcharge possible
    pour le test de connexion depuis les réglages.
    """

    def __init__(self, env, base_url=None, api_key=None):
        self.env = env
        icp = env['ir.config_parameter']
        self.base_url = base_url or icp.get_str('mailcow.base_url', default='')
        self.api_key = api_key or icp.get_str('mailcow.api_key', default='')

    def _request(self, method, path, payload=None):
        """Appelle l'API et renvoie la liste ``data`` de la réponse Mailcow."""
        if not self.base_url or not self.api_key:
            raise MailcowAPIError(
                "Le serveur Mailcow n'est pas configuré. Renseignez l'URL de base "
                "(paramètre « mailcow.base_url ») et la clé API (paramètre "
                "« mailcow.api_key ») dans Réglages > Mailcow."
            )
        url = self.base_url.rstrip('/') + '/api/v1' + path
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method=method.upper(),
        )
        # Conservation du nom d'en-tête exact attendu par Mailcow :
        # Request.add_header() capitalise les noms (X-api-key), ce qui
        # casserait une recherche sensible à la casse.
        request.headers['X-API-Key'] = self.api_key
        for tentative in (1, 2, 3):
            try:
                with urllib.request.urlopen(request) as response:
                    body = response.read().decode('utf-8')
                break
            except urllib.error.HTTPError as error:
                # 429 et les 5xx sont passagers : on reprend avant d'abandonner.
                if error.code in (429, 500, 502, 503, 504) and tentative < 3:
                    time.sleep(tentative)
                    continue
                raise MailcowAPIError(
                    'Échec de l\'appel à l\'API Mailcow (HTTP %d, %s %s) : %s'
                    % (error.code, method.upper(), path, error.reason)
                ) from error
            except urllib.error.URLError as error:
                if tentative < 3:
                    time.sleep(tentative)
                    continue
                raise MailcowAPIError(
                    'Serveur Mailcow inaccessible (%s) : %s' % (url, error.reason)
                ) from error
        try:
            result = json.loads(body)
        except json.JSONDecodeError as error:
            raise MailcowAPIError(
                'Réponse illisible de l\'API Mailcow pour %s.' % path
            ) from error
        if result is None:
            return []
        entries = result.get('data') if isinstance(result, dict) and 'data' in result else result
        if entries is None:
            raise MailcowAPIError('Réponse inattendue de Mailcow pour %s.' % path)
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            raise MailcowAPIError('Réponse inattendue de Mailcow pour %s.' % path)
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get('type') in ('danger', 'error'):
                raise MailcowAPIError(
                    entry.get('msg') or 'Erreur Mailcow non détaillée.'
                )
            if entry.get('msg'):
                self._notify(entry)
        return entries

    def _notify(self, entry):
        """Pousse une notification dans le client Odoo (best effort)."""
        try:
            self.env['bus.bus']._sendone(
                'mailcow',
                {
                    'type': 'notification',
                    'data': {
                        'title': 'Mailcow',
                        'message': entry['msg'],
                        'type': 'success' if entry.get('type') == 'success' else 'info',
                        'sticky': True,
                        'stacked': True,
                    },
                },
            )
        except Exception:  # noqa: BLE001 - la notification ne doit pas casser l'action
            pass