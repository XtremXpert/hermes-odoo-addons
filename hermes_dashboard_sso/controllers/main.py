import json
from urllib.parse import urlencode

from werkzeug.exceptions import BadRequest
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request

from ..models.sso_code import LEVELS


def callback_url(level):
    """The only redirect target accepted: the dashboard of that level on this host."""
    return request.httprequest.host_url.rstrip("/") + f"/hermes/{level}/auth/callback"


class HermesDashboardSso(http.Controller):
    @http.route(
        "/hermes/sso/authorize",
        type="http",
        auth="user",
        methods=["GET"],
        readonly=False,
        sitemap=False,
    )
    def authorize(
        self,
        level=None,
        redirect_uri=None,
        state=None,
        code_challenge=None,
        code_challenge_method=None,
        **kwargs,
    ):
        """Émet un code d'autorisation SSO pour un administrateur.

        Args:
            level: Niveau Hermes demandé.
            redirect_uri: URL de retour, qui doit être le callback du niveau.
            state: État à renvoyer tel quel au client.
            code_challenge: Défi PKCE du client.
            code_challenge_method: Méthode du défi, ``S256`` uniquement.
            **kwargs: Paramètres supplémentaires ignorés.

        Returns:
            Redirection vers le callback avec le code et l'état.

        Raises:
            Forbidden: Demandeur sans droit administrateur.
            BadRequest: Paramètres manquants ou invalides.
        """
        if not request.env.user.has_group("base.group_system"):
            raise Forbidden()
        if (
            level not in LEVELS
            or redirect_uri != callback_url(level)
            or not state
            or not code_challenge
            or code_challenge_method != "S256"
        ):
            raise BadRequest()
        code = request.env["hermes.dashboard.sso.code"]._issue(
            request.env.user, level, redirect_uri, code_challenge
        )
        return request.redirect(
            redirect_uri + "?" + urlencode({"code": code, "state": state}), local=False
        )

    @http.route(
        "/hermes/sso/token",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
        readonly=False,
        sitemap=False,
    )
    def token(self, **kwargs):
        """Échange un code d'autorisation contre l'identité SSO.

        Args:
            **kwargs: Paramètres de la requête.

        Returns:
            Réponse JSON avec l'identité, ou une erreur ``invalid_grant`` en 400.
        """
        try:
            body = json.loads(request.httprequest.get_data() or b"{}")
        except ValueError:
            body = {}
        identity = (
            request.env["hermes.dashboard.sso.code"]
            .sudo()
            ._redeem(
                body.get("code"),
                body.get("code_verifier"),
                body.get("level"),
                body.get("redirect_uri"),
            )
        )
        status = 200 if identity else 400
        return request.make_json_response(identity or {"error": "invalid_grant"}, status=status)
