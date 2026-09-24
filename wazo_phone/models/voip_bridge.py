# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Pont softphone vers le module « voip » d'Odoo Enterprise.

Le module « voip » (nom affiché : « Phone ») fournit un softphone
WebRTC dans le navigateur (SIP-over-WebSocket). Pour cela il attend :

- un ``voip.provider`` (URL WebSocket + domaine SIP du PBX) ;
- des identifiants sur ``res.users`` (``voip_username`` /
  ``voip_secret``), qui se répercutent sur ``res.users.settings``.

Ce pont crée un provider « Wazo » à partir de la configuration Wazo
et propage les identifiants SIP générés par la synchronisation vers
les utilisateurs Odoo liés aux utilisateurs Wazo.

Le module « voip » n'est PAS une dépendance requise : lorsqu'il n'est
pas installé, toutes les opérations ici sont des no-ops (le module
reste utilisable tel quel, avec poste SIP classique).
"""

import logging

from odoo import api, fields, models

from ..services.wazo_client import WazoAPIError

_logger = logging.getLogger(__name__)

#: Nom du provider ``voip.provider`` créé pour Wazo.
VOIP_PROVIDER_NAME = 'Wazo'

#: Chemin du point d'accès WebSocket SIP exposé par Wazo (Asterisk).
#: C'est ce chemin qu'utilisent le web client Wazo et le module « voip »
#: d'Enterprise pour un softphone WebRTC dans le navigateur.
ASTERISK_WS_PATH = '/api/asterisk/ws'

#: Options d'endpoint PJSIP rendant l'endpoint WebRTC-capable.
#: Réplique les options d'endpoint du template SIP « webrtc » de Wazo
#: (tel que rendu pour l'endpoint de référence « webrtc1001 ») :
#: codecs audio/vidéo du navigateur, ICE, négociation SDP (AVPF),
#: chiffrement DTLS et média direct. Le transport ``wss`` est hérité
#: de l'endpoint ; l'option ``allow`` active les codecs du navigateur.
WEBRTC_ENDPOINT_OPTIONS = [
    ['allow', 'opus,g722,alaw,ulaw,vp9,vp8,h264'],
    ['ice_support', 'yes'],
    ['use_avpf', 'yes'],
    ['media_encryption', 'dtls'],
    ['dtls_verify', 'no'],
    ['direct_media', 'yes'],
]


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    wazo_softphone_enabled = fields.Boolean(
        string='Softphone (voip)', default=True,
        config_parameter='wazo.softphone_enabled',
        help="Active le pont softphone (nécessite le module 'voip' "
             "d'Enterprise installé et le transport wss d'Asterisk "
             "sur le serveur Wazo).")
    wazo_ws_url = fields.Char(
        string='URL WebSocket (wss)', config_parameter='wazo.ws_url',
        help='ex : wss://wazo.diverse-cite.com')
    wazo_pbx_domain = fields.Char(
        string='Domaine SIP (PBX)', config_parameter='wazo.pbx_domain',
        help='Domaine utilisé dans les URI SIP '
             '(ex : wazo.diverse-cite.com).')

    def action_ensure_voip_provider(self):
        """(Re)crée le provider Wazo et propage les identifiants SIP de
        tous les utilisateurs synchronisés."""
        self.ensure_one()
        self.execute()
        self.env['wazo.user'].sudo()._propagate_voip_credentials()


class WazoUserVoipBridge(models.Model):
    _inherit = 'wazo.user'

    # ------------------------------------------------------------------
    # Disponibilité du pont
    # ------------------------------------------------------------------

    def _voip_available(self):
        """Indique si le pont softphone est opérationnel.

        Vrai uniquement si le module « voip » est chargé, que le pont
        n'est pas explicitement désactivé, et qu'une URL WebSocket est
        configurée.
        """
        if 'voip.provider' not in self.env.registry:
            return False
        icp = self.env['ir.config_parameter'].sudo()
        if icp.get_str('wazo.softphone_enabled', default='True') in (
                'False', 'false', '0'):
            return False
        return bool(icp.get_str('wazo.ws_url', default=''))

    # ------------------------------------------------------------------
    # Helpers WebRTC (endpoint + URL WebSocket)
    # ------------------------------------------------------------------

    @api.model
    def _build_endpoint_sip_payload(self, context, extension, templates=None):
        """Construit le payload ``endpoint_sip`` WebRTC-capable.

        Voie native (spec P3 v3) : lorsque les templates SIP du tenant
        sont connus (``global`` + ``webrtc``, voir
        ``_get_sip_template_uuids``), l'endpoint s'y **réfère**. Les
        options WebRTC (``webrtc=yes``, codecs, ICE/AVPF/DTLS, transport
        ``wss``) viennent alors de Wazo lui-même, au lieu d'une réplique
        locale qui dérive à chaque évolution de la plateforme — la
        réplique ``WEBRTC_ENDPOINT_OPTIONS`` avait ainsi déjà perdu
        ``webrtc=yes`` et contredisait ``direct_media``.

        Le ``context``, lui, n'est porté par aucun des deux templates : il
        reste explicite sur l'endpoint.

        Sans template résolu (résolution impossible), on retombe sur la
        réplique locale afin de ne jamais créer silencieusement un
        endpoint non-WebRTC.

        Facteuré ici afin que la logique soit testable et réutilisable par
        le flux de synchronisation.
        """
        endpoint_sip = {
            'auth_section_options': [
                ['username', str(extension)],
            ],
            'endpoint_section_options': [
                ['context', str(context)],
            ],
        }
        # L'ordre est significatif : ``global`` d'abord, ``webrtc``
        # ensuite (le second surcharge le premier).
        sip_templates = [
            {'uuid': uuid}
            for uuid in (
                (templates or {}).get('global'),
                (templates or {}).get('webrtc'),
            )
            if uuid
        ]
        if sip_templates:
            endpoint_sip['templates'] = sip_templates
        else:
            endpoint_sip['endpoint_section_options'] += [
                list(option) for option in WEBRTC_ENDPOINT_OPTIONS]
        return {'endpoint_sip': endpoint_sip}

    @api.model
    def _get_sip_template_uuids(self, client):
        """Résout les UUID des templates SIP du tenant Wazo.

        ``GET /tenants/<uuid>`` porte ``global_sip_template_uuid`` et
        ``webrtc_sip_template_uuid``. Résolu en direct plutôt que mis en
        cache : l'UUID change si le tenant est réinitialisé, et le coût
        est un simple GET de configuration.

        Défensif : retourne ``{}`` (donc repli sur les options locales) si
        le tenant n'est pas configuré, si l'appel échoue, ou si la réponse
        n'a pas la forme attendue. Une synchronisation ne doit jamais
        échouer parce qu'un template n'a pas pu être résolu.
        """
        tenant_uuid = getattr(client, 'tenant_id', False)
        if not tenant_uuid:
            return {}
        try:
            tenant = client.conf('GET', '/tenants/%s' % tenant_uuid)
        except WazoAPIError:
            return {}
        if not isinstance(tenant, dict):
            return {}
        return {
            'global': tenant.get('global_sip_template_uuid') or False,
            'webrtc': tenant.get('webrtc_sip_template_uuid') or False,
        }

    @api.model
    def _get_voip_ws_url(self):
        """Retourne l'URL WebSocket SIP (``wss://…``) du softphone.

        Si un URL est explicitement défini (``wazo.ws_url``), il est
        utilisé tel quel. Sinon, il est dérivé de l'URL Wazo
        (``wazo.url``) en forçant le schéma ``wss`` et en ajoutant le
        chemin du point d'accès Asterisk.
        """
        icp = self.env['ir.config_parameter'].sudo()
        explicit = icp.get_str('wazo.ws_url', default='')
        if explicit:
            return explicit
        wazo_url = icp.get_str('wazo.url', default='')
        if not wazo_url:
            return ''
        # https://hote[:port] → wss://hote[:port]/api/asterisk/ws
        base = wazo_url.split('//', 1)[-1]
        return 'wss://' + base + ASTERISK_WS_PATH

    def _get_or_create_voip_provider(self):
        """Retourne le ``voip.provider`` « Wazo » (créé si nécessaire).

        Retourne un recordset vide si le pont est indisponible (module
        absent ou non configuré).
        """
        if not self._voip_available():
            return self.env['ir.model'].browse()
        icp = self.env['ir.config_parameter'].sudo()
        provider = self.env['voip.provider'].sudo().search(
            [('name', '=', VOIP_PROVIDER_NAME)], limit=1)
        values = {
            'ws_server': icp.get_str('wazo.ws_url', default=''),
            'pbx_ip': icp.get_str('wazo.pbx_domain', default=''),
            'mode': 'prod',
        }
        if provider:
            provider.write(values)
        else:
            provider = self.env['voip.provider'].sudo().create({
                'name': VOIP_PROVIDER_NAME, **values})
        return provider

    # ------------------------------------------------------------------
    # Propagation des identifiants
    # ------------------------------------------------------------------

    def _voip_user_values(self, provider):
        """Valeurs à écrire sur un utilisateur Odoo pour le softphone.

        Retourne un dictionnaire vide si la propagation n'est pas
        applicable (pas de provider ou pas d'identifiants SIP).
        """
        self.ensure_one()
        if not (provider and self.sip_username):
            return {}
        return {
            'voip_provider_id': provider.id,
            'voip_username': self.sip_username,
            'voip_secret': self.sip_password,
        }

    def _apply_voip_user_values(self, user, values):
        """Écrit les valeurs softphone sur l'utilisateur.

        Isolée dans une méthode dédiée afin d'être mockable en test
        (le champ ``voip_username`` n'existe que si « voip » est
        installé).
        """
        user.sudo().write(values)

    def _voip_username_of(self, user):
        """Lit l'identifiant softphone courant de l'utilisateur.

        Isolée pour les tests (le champ n'existe que si « voip » est
        installé).
        """
        return user.sudo().voip_username

    def _propagate_voip_credentials(self):
        """Propage les identifiants SIP Wazo vers les utilisateurs
        Odoo liés.

        N'envoie jamais d'exception : un échec inattendu du pont ne
        doit pas annuler la synchronisation Wazo, déjà définitive sur
        le serveur distant (les échecs sont consignés dans les logs).
        """
        provider = self._get_or_create_voip_provider()
        for wiz in self:
            for user in wiz.partner_id.user_ids:
                try:
                    values = wiz._voip_user_values(provider)
                    if not values:
                        continue
                    self._apply_voip_user_values(user, values)
                except Exception:
                    _logger.exception(
                        'Pont softphone : impossible de propager les '
                        'identifiants SIP de l\'utilisateur Wazo %r '
                        'vers l\'utilisateur Odoo %r.',
                        wiz.name, user.login)
        return True

    def _revoke_voip_credentials(self):
        """Révoque les identifiants softphone (suppression distante).

        Ne révoque que si les identifiants en place proviennent bien
        de Wazo (identifiant SIP identique). Comme la propagation,
        n'envoie jamais d'exception.
        """
        for wiz in self:
            for user in wiz.partner_id.user_ids:
                try:
                    if (wiz.sip_username
                            and self._voip_username_of(user) == wiz.sip_username):
                        self._apply_voip_user_values(user, {
                            'voip_username': False,
                            'voip_secret': False,
                        })
                except Exception:
                    _logger.exception(
                        'Pont softphone : impossible de révoquer les '
                        'identifiants SIP de l\'utilisateur Wazo %r '
                        'vers l\'utilisateur Odoo %r.',
                        wiz.name, user.login)
        return True