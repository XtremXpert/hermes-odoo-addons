import json
from urllib.parse import parse_qs
from urllib.parse import urlsplit

from odoo.tests import HttpCase
from odoo.tests import tagged

from ..models.sso_code import s256


@tagged("post_install", "-at_install")
class TestDashboardSso(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        cls.admin = Users.create(
            {
                "name": "Admin SSO",
                "login": "sso_admin",
                "password": "sso_admin_pw_1234",
                "group_ids": [(6, 0, [cls.env.ref("base.group_system").id])],
            }
        )
        cls.member = Users.create(
            {
                "name": "Membre SSO",
                "login": "sso_member",
                "password": "sso_member_pw_1234",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.verifier = "v" * 50

    def authorize(self, level="n2", redirect=None, challenge=None):
        base = self.base_url()
        redirect = redirect or f"{base}/hermes/{level}/auth/callback"
        return self.url_open(
            "/hermes/sso/authorize?"
            + "&".join(
                [
                    f"level={level}",
                    f"redirect_uri={redirect}",
                    "state=etat",
                    "code_challenge_method=S256",
                    f"code_challenge={challenge or s256(self.verifier)}",
                ]
            ),
            allow_redirects=False,
        ), redirect

    def token(self, code, level="n2", redirect=None, verifier=None):
        body = {
            "code": code,
            "code_verifier": verifier or self.verifier,
            "level": level,
            "redirect_uri": redirect or f"{self.base_url()}/hermes/{level}/auth/callback",
        }
        return self.url_open(
            "/hermes/sso/token", data=json.dumps(body), headers={"Content-Type": "application/json"}
        )

    def test_admin_code_exchanges_once_for_the_identity(self):
        self.authenticate("sso_admin", "sso_admin_pw_1234")
        response, redirect = self.authorize()
        self.assertEqual(response.status_code, 303)
        location = urlsplit(response.headers["Location"])
        self.assertEqual(f"{location.scheme}://{location.netloc}{location.path}", redirect)
        query = parse_qs(location.query)
        self.assertEqual(query["state"], ["etat"])
        code = query["code"][0]
        self.assertEqual(
            self.token(code, verifier="w" * 50).status_code, 400
        )  # wrong verifier burns it
        response, _ = self.authorize()
        code = parse_qs(urlsplit(response.headers["Location"]).query)["code"][0]
        first = self.token(code)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["login"], "sso_admin")
        self.assertEqual(self.token(code).status_code, 400)  # single use

    def test_only_administrators_and_only_the_dashboard_callback(self):
        self.authenticate("sso_member", "sso_member_pw_1234")
        self.assertEqual(self.authorize()[0].status_code, 403)
        self.authenticate("sso_admin", "sso_admin_pw_1234")
        self.assertEqual(
            self.authorize(redirect="https://evil.example/hermes/n2/auth/callback")[0].status_code,
            400,
        )
        self.assertEqual(self.authorize(level="n4")[0].status_code, 400)
        response, _ = self.authorize(level="n1")
        code = parse_qs(urlsplit(response.headers["Location"]).query)["code"][0]
        self.assertEqual(self.token(code, level="n2").status_code, 400)  # code bound to its level

    def test_code_is_refused_after_the_user_loses_administrator_rights(self):
        self.authenticate("sso_admin", "sso_admin_pw_1234")
        response, _ = self.authorize()
        code = parse_qs(urlsplit(response.headers["Location"]).query)["code"][0]
        self.admin.group_ids = [(3, self.env.ref("base.group_system").id)]
        self.assertEqual(self.token(code).status_code, 400)
