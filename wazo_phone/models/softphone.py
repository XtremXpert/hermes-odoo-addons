# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Configuration softphone pour le navigateur (P3.3 — voie native v3).

Ce mixin expose la configuration complète que le softphone SIP.js
(intégré dans l'onglet Discuss) utilise pour joindre **directement
Wazo** en SIP-over-WSS : l'URL WebSocket de Wazo, l'AOR (nom
d'endpoint), l'identifiant et le mot de passe d'authentification SIP,
et le domaine PBX.

**Pas de relay** : le navigateur parle à Wazo sur un endpoint WebRTC
natif (`transport-wss` + template `webrtc` côté confd, voir la spec
P3 v3, section NORMATIF). Le paramètre `wazo.softphone_ws_url` de la
v2 (relay B2BUA Sippy) n'est plus consulté.

Point critique (découverte P3.2) : pour un endpoint **généré** par
Wazo confgen, l'AOR (la valeur de l'en-tête ``From`` de SIP) est le
**nom de l'endpoint** (une chaîne aléatoire, ex. ``m0kxsfvz``), et
NON l'extension. L'authentification SIP utilise le **username** =
l'extension. Ces deux valeurs sont donc portées séparément
(``aor`` et ``auth_user``) dans la configuration.

Ce module est indépendant du module « voip » d'Enterprise : il sert
NOTRE softphone, et n'est jamais un no-op de disponibilité.
"""

from odoo import fields
from odoo import models


class WazoUserSoftphone(models.Model):
    _inherit = 'wazo.user'

    #: Nom de l'endpoint SIP généré par Wazo confgen (= nom de l'AOR
    #: utilisé dans l'en-tête ``From`` de SIP). Différent de
    #: l'extension pour un endpoint généré ; identique à l'extension
    #: pour un endpoint manuel.
    remote_endpoint_name = fields.Char(
        string='Nom d’endpoint Wazo (AOR)',
        help="Nom de l’endpoint SIP côté Wazo. C’est la valeur de "
             "l’en-tête From du softphone (découverte P3.2 : pour un "
             "endpoint généré, ce nom n’est pas l’extension).")

    # ------------------------------------------------------------------
    # Composants de la configuration
    # ------------------------------------------------------------------

    def _softphone_aor(self):
        """Retourne le nom d'AOR du softphone (en-tête ``From``).

        Le nom d'endpoint connu (capturé à la synchro) est utilisé ;
        en l'absence, l'extension est retournée (cas d'un endpoint
        manuel dont l'AOR est l'extension).
        """
        self.ensure_one()
        return self.remote_endpoint_name or self.extension or False

    def _softphone_ws_url(self):
        """Retourne l'URL SIP-over-WSS que le softphone doit joindre.

        **Voie native (v3)** : le navigateur parle directement à Wazo,
        donc l'URL est celle de l'endpoint WebRTC :

        1. ``wazo.ws_url`` — l'URL WebSocket de Wazo (celle du pont
           Asterisk, ``/api/asterisk/ws``) ;
        2. à défaut, dérivée de ``wazo.url`` (voir ``_get_voip_ws_url``).

        Le paramètre ``wazo.softphone_ws_url`` de la v2, qui servait à
        pointer le softphone sur le relay B2BUA, n'est **plus consulté**
        (l'override relay est ignoré par contrat).
        """
        self.ensure_one()
        return self._get_voip_ws_url()

    def _softphone_domain(self):
        """Retourne le domaine SIP (PBX) utilisé dans les URI."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        return (icp.get_str('wazo.pbx_domain', default='') or 'asterisk')

    def _softphone_enabled(self):
        """Le softphone est-il activé (paramètre, défaut : oui)."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        value = icp.get_str('wazo.softphone_enabled', default='True')
        return value not in ('False', 'false', '0')

    #: Moteurs SIP reconnus par le softphone du navigateur.
    #:
    #: * ``wazo_sdk`` — client officiel Wazo (``WebRTCClient`` du bundle
    #:   vendorisé ``wazo_phone.assets_sdk``). C'est le moteur **retenu**
    #:   (décision P3.3f) : il fournit l'attachement du média distant,
    #:   la reconnexion ICE, le heartbeat de transport et les stats réseau.
    #: * ``sipjs`` — couche SIP.js écrite à la main (P3.3a/b), conservée
    #:   comme repli. Elle **n'attache pas l'audio distant** : un appel
    #:   s'établit mais reste muet. À n'utiliser que pour comparer.
    SOFT_PHONE_ENGINES = ('wazo_sdk', 'sipjs')

    #: Moteur utilisé par défaut et pour toute valeur inconnue.
    SOFT_PHONE_DEFAULT_ENGINE = 'wazo_sdk'

    def _softphone_engine(self):
        """Retourne le moteur SIP que le navigateur doit utiliser.

        Lit ``wazo.softphone_engine``. Toute valeur absente ou inconnue
        retombe sur le moteur retenu (jamais sur « rien » : un softphone
        sans moteur serait un softphone muet).
        """
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        value = (icp.get_str('wazo.softphone_engine', default='') or '').strip()
        if value not in self.SOFT_PHONE_ENGINES:
            return self.SOFT_PHONE_DEFAULT_ENGINE
        return value

    # ------------------------------------------------------------------
    # Configuration exposée au navigateur
    # ------------------------------------------------------------------

    def get_softphone_config(self):
        """Assemble la configuration softphone pour le navigateur.

        Retourne un dictionnaire (ou ``{}`` si l'utilisateur n'est pas
        prêt — non synchronisé, sans identifiants SIP, ou softphone
        désactivé) :

        - ``enabled``       : le softphone est actif ;
        - ``ws_url``        : l'URL SIP-over-WSS de Wazo (endpoint WebRTC
          natif, ``/api/asterisk/ws``) ;
        - ``aor``           : le nom d'AOR (en-tête From) ;
        - ``auth_user``     : l'identifiant d'auth SIP (extension) ;
        - ``auth_password`` : le mot de passe de registration ;
        - ``domain``        : le domaine SIP (PBX) ;
        - ``display_name``  : le nom affiché ;
        - ``extension``     : le poste ;
        - ``engine``        : le moteur SIP à charger (``wazo_sdk`` ou
          ``sipjs``) — voir ``_softphone_engine``.

        Le mot de passe est lu en ``sudo`` : la méthode est la
        frontière d'accréditation ; le contrôleur d'appel (P3.3
        frontend) garantit que l'utilisateur ne récupère QUE sa propre
        configuration.
        """
        self.ensure_one()
        if self.wazo_state != 'synced' or not self.sip_username:
            return {}
        if not self._softphone_enabled():
            return {}
        wiz = self.sudo()
        return {
            'enabled': True,
            'ws_url': self._softphone_ws_url(),
            'aor': self._softphone_aor(),
            'auth_user': wiz.sip_username,
            'auth_password': wiz.sip_password,
            'domain': self._softphone_domain(),
            'display_name': self.name,
            'extension': self.extension,
            'engine': self._softphone_engine(),
        }


class ResUsersWazoSoftphone(models.Model):
    """Méthodes softphone côté navigateur (P3.3b) sur ``res.users``.

    Le contrôleur web appelle ces méthodes en passant l'ID de l'utilisateur
    courant (le framework ``call_kw`` browse ``res.users`` avec cet ID).
    Elles résolvent l'utilisateur Wazo lié au contact de l'utilisateur,
    puis délèguent à ``wazo.user``.

    Ceci corrige le câblage du P3.3a : l'ancien appel frontend passait
    l'ID ``res.users`` au modèle ``wazo.user`` (browse par coïncidence
    d'ID SQL, non fiable). Ici le modèle browse est le bon (``res.users``).
    """
    _inherit = 'res.users'

    def get_wazo_softphone_config(self):
        """Configuration softphone de l'utilisateur courant.

        Retourne le dictionnaire de ``wazo.user.get_softphone_config`` (ou
        ``{}`` si l'utilisateur n'a pas d'utilisateur Wazo synchronisé).
        """
        self.ensure_one()
        wiz = self.wazo_user_id
        return wiz.get_softphone_config() if wiz else {}

    def get_wazo_call_log(self, limit=50):
        """Journal d'appels (CDR) de l'utilisateur, le plus récent d'abord.

        Un appel « de l'utilisateur » est un CDR dont l'appelant OU la
        destination est l'extension Wazo de l'utilisateur. Retourne une
        liste de dictionnaires (bornée par ``limit``) ; chaque entrée
        porte l'autre partie de l'appel (numéro, nom, contact identifié).
        """
        self.ensure_one()
        wiz = self.wazo_user_id
        if not wiz or not wiz.extension:
            return []
        ext = wiz.extension
        domain = [
            '|',
            ('caller_num', '=', ext),
            ('destination_num', '=', ext),
        ]
        cdrs = self.env['wazo.cdr'].search(
            domain, limit=limit, order='date_start desc')
        return [self._cdr_to_entry(cdr) for cdr in cdrs]

    def _cdr_to_entry(self, cdr):
        """Convertit un CDR en entrée du journal (vue navigateur).

        L'« autre partie » dépend du sens : l'appelant pour un appel
        entrant, la destination pour un appel sortant/interne.
        """
        if cdr.call_direction == 'inbound':
            num, name = cdr.caller_num, cdr.caller_name
        else:
            num, name = cdr.destination_num, cdr.destination_name
        return {
            'id': cdr.id,
            'date': cdr.date_start.isoformat() if cdr.date_start else False,
            'direction': cdr.call_direction,
            'answered': cdr.answered,
            'duration': cdr.duration,
            'num': num,
            'name': name,
            'partner_id': cdr.partner_id.id if cdr.partner_id else False,
            'partner_name': (
                cdr.partner_id.display_name if cdr.partner_id else False),
        }
