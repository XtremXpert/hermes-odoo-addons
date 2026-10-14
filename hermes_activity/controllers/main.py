# Copyright 2026 Bemade Inc., Benoît Vézina — AGPL-3
"""Le contrôleur derrière les boutons d'approbation de Hermes.

Repris de hermes_boutons (mac-demo, Bemade Inc.), durci pour maison. Un bouton
poste la commande dans le canal AU NOM DE LA PERSONNE QUI CLIQUE (aucun sudo) :
la garde d'auteur de Hermes la valide comme un message tapé, et un clic hors
du groupe autorisé est posté puis ignoré. Le contrôleur n'accorde aucun pouvoir.

AUCUNE ÉCRITURE SUR UN GET. L'original écrivait sur un GET sans jeton CSRF. Or
du HTML écrit par un agent (une note, une réponse) passe le nettoyeur d'Odoo :
une <img src="/hermes/repondre?…&cmd=/approve"> aurait fait approuver une
commande par le simple affichage du message, sans clic. Ici :
  - le clic passe par /hermes/approbation (JSON-RPC, corps JSON : ni une image
    ni un formulaire d'un autre site ne peuvent le produire) ;
  - sans JavaScript, le lien mène à une page de confirmation dont le
    formulaire POST porte le jeton CSRF d'Odoo.

LISTE BLANCHE STRICTE des commandes, et la personne doit être membre du canal.
"""

from markupsafe import Markup
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

_COMMANDES = {
    prefixe + commande
    for prefixe in ("/", "!", ".")
    for commande in ("approve", "approve session", "approve always", "deny")
}


def _canal(canal, cmd):
    if cmd not in _COMMANDES:
        raise NotFound()
    try:
        canal_id = int(canal)
    except (TypeError, ValueError):
        raise NotFound() from None
    channel = request.env["discuss.channel"].browse(canal_id).exists()
    membre = request.env["discuss.channel.member"].search_count(
        [("channel_id", "=", canal_id), ("partner_id", "=", request.env.user.partner_id.id)]
    )
    if not channel or not membre:
        raise NotFound()
    return channel


def _poster(channel, cmd):
    # COMME L'UTILISATEUR : si l'accès au canal lui est refusé, l'exception
    # d'Odoo fait foi.
    return channel.message_post(body=cmd, message_type="comment", subtype_xmlid="mail.mt_comment")


class HermesApprobation(http.Controller):
    @http.route("/hermes/approbation", type="jsonrpc", auth="user", methods=["POST"])
    def approbation(self, canal=None, cmd=None):
        return {"message_id": _poster(_canal(canal, cmd), cmd).id}

    @http.route("/hermes/repondre", type="http", auth="user", methods=["GET"])
    def confirmer(self, canal=None, cmd=None, **kwargs):
        # Repli sans JavaScript : une page de confirmation, rien n'est posté.
        channel = _canal(canal, cmd)
        page = Markup(
            "<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
            "<title>Réponse à Hermes</title></head><body>"
            "<p>Envoyer <code>%s</code> dans « %s » ?</p>"
            "<form method='post' action='/hermes/repondre'>"
            "<input type='hidden' name='csrf_token' value='%s'>"
            "<input type='hidden' name='canal' value='%s'>"
            "<input type='hidden' name='cmd' value='%s'>"
            "<button type='submit'>Envoyer</button> <a href='/odoo/discuss'>Annuler</a>"
            "</form></body></html>"
        ) % (cmd, channel.name, request.csrf_token(), channel.id, cmd)
        return request.make_response(page, headers=[("Content-Type", "text/html; charset=utf-8")])

    @http.route("/hermes/repondre", type="http", auth="user", methods=["POST"])
    def envoyer(self, canal=None, cmd=None, **kwargs):
        # csrf=True (défaut d'Odoo) : un formulaire d'un autre site est refusé.
        channel = _canal(canal, cmd)
        _poster(channel, cmd)
        return request.redirect("/odoo/discuss?active_id=discuss.channel_%d" % channel.id)
