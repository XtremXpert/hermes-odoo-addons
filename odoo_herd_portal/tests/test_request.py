import json
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tests import HttpCase
from odoo.tests import TransactionCase
from odoo.tests import new_test_user
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import DIGEST_A
from .common import HerdPortalMixin


class HerdRequestMixin(HerdPortalMixin):
    @classmethod
    def _herd_request_setup(cls):
        cls._herd_setup()
        env = cls.env
        cls.offer = env["k8s.odoo.instance.template"].create(
            {
                "name": "Standard",
                "image": DIGEST_A,
                "cluster_issuer": "letsencrypt",
                "filestore_size": "5Gi",
                "filestore_storage_class": "longhorn",
                "herd_portal_published": True,
                "herd_cluster_id": cls.cluster.id,
                "herd_namespace": "odoo-clients",
                "herd_host_suffix": "clients.example.com",
                "herd_portal_description": "One production and its staging.",
            }
        )
        cls.manager = new_test_user(
            env,
            login="herd_manager",
            groups="base.group_user,odoo_herd.group_k8s_manager",
            email="manager@example.com",
            name="Manager",
        )
        # other_client has no production: its user may ask for a database.
        cls.newcomer = cls.stranger

    def _request_mocks(self):
        """Mock the cluster: instance creation, RPC and host patch."""
        self.rpc_calls = []
        self.patched_hosts = []
        self.commits = []
        self.rpc_uid = 2
        env = self.env
        Request = type(env["k8s.odoo.instance.request"])

        def create_instance(req, staging=False):
            name = f"{req.instance_name}-staging" if staging else req.instance_name
            vals = {
                "cluster_id": req.template_id.herd_cluster_id.id,
                "namespace": req.template_id.herd_namespace,
                "name": name,
                "environment": "staging" if staging else "production",
                "image": DIGEST_A,
            }
            if staging:
                vals["production_instance_id"] = req.production_id.id
            return env["k8s.odoo.instance"].sudo().create(vals)

        def rpc(req, instance, service, method, *args):
            self.rpc_calls.append((instance.name, service, method, args))
            if method == "authenticate":
                return self.rpc_uid
            return True

        stack = patch.multiple(
            Request,
            _herd_create_instance=lambda req, staging=False: create_instance(req, staging),
            _herd_rpc=lambda req, instance, service, method, *args: rpc(
                req, instance, service, method, *args
            ),
            _herd_patch_hosts=lambda req, instance, host: self.patched_hosts.append(
                (instance.name, host)
            ),
            _herd_commit=lambda req: self.commits.append(
                bool(self.env["mail.mail"].sudo().search_count([("auto_delete", "=", True)]))
            ),
        )
        stack.start()
        self.addCleanup(stack.stop)

    def _ask(self, user=None, name="newshop"):
        Request = self.env["k8s.odoo.instance.request"].with_user(user or self.newcomer)
        return Request.browse(Request.herd_request_database(self.offer.id, name)).sudo()


@tagged("post_install", "-at_install")
class TestHerdRequest(HerdRequestMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._herd_request_setup()

    def setUp(self):
        super().setUp()
        self._request_mocks()

    def test_name_rules(self):
        Request = self.env["k8s.odoo.instance.request"]
        for bad in ("ab", "1shop", "Shop!", "shop-", "my--shop", "a" * 31):
            with self.assertRaises(ValidationError, msg=bad):
                Request._herd_clean_name(bad)
        for reserved in ("maison", "www", "shop-staging"):
            with self.assertRaises(ValidationError, msg=reserved):
                Request._herd_clean_name(reserved)
        self.assertEqual(Request._herd_clean_name("  My-Shop2 "), "my-shop2")

    def test_name_already_taken(self):
        with self.assertRaises(ValidationError):
            self._ask(name="shop")  # existing production of the test cluster
        self.prod.current_ingress_hosts = "taken.clients.example.com, www.shop.example.com"
        with self.assertRaises(ValidationError):
            self._ask(name="taken")

    def test_request_rules(self):
        req = self._ask()
        self.assertEqual(req.state, "requested")
        self.assertEqual(req.partner_id, self.other_client)
        self.assertEqual(req.host, "newshop.clients.example.com")
        self.assertEqual(req.staging_host, "newshop-staging.clients.example.com")
        # one open request per client
        with self.assertRaises(UserError):
            self._ask(name="another")
        # a client with a production gets no new database
        with self.assertRaises(UserError):
            self._ask(user=self.client_user, name="third")
        # agents never ask
        with self.assertRaises(AccessError):
            self._ask(user=self.agent, name="fourth")
        Request = self.env["k8s.odoo.instance.request"]
        self.assertFalse(Request._herd_can_request(self.newcomer))
        self.assertFalse(Request._herd_can_request(self.client_user))

    def test_unpublished_offer_refused(self):
        self.offer.herd_portal_published = False
        self.assertFalse(self.env["k8s.odoo.instance.request"]._herd_can_request(self.newcomer))
        with self.assertRaises(UserError):
            self._ask()

    def test_only_a_human_manager_approves(self):
        req = self._ask()
        for user in (self.newcomer, self.approver, self.agent):
            with self.assertRaises(AccessError):
                req.with_user(user).action_herd_approve()
        self.agent.group_ids += self.env.ref("odoo_herd.group_k8s_manager")
        with self.assertRaises(AccessError):
            req.with_user(self.agent).action_herd_approve()
        self.assertEqual(req.state, "requested")

    def test_full_flow(self):
        req = self._ask()
        req.with_user(self.manager).action_herd_approve()
        self.assertEqual(req.state, "creating")
        self.assertEqual(req.approved_by_id, self.manager)
        prod = req.production_id
        self.assertEqual(prod.herd_partner_id, self.other_client)
        self.assertEqual(prod.herd_approver_ids, self.newcomer)

        # not running yet: nothing happens
        self.env["k8s.odoo.instance.request"]._cron_herd_requests()
        self.assertEqual(req.state, "creating")
        self.assertFalse(self.rpc_calls)

        prod.phase = "Running"
        self.env["k8s.odoo.instance.request"]._cron_herd_requests()
        self.assertEqual(req.state, "cloning")
        auth = self.rpc_calls[0]
        self.assertEqual(auth[:3], ("newshop", "common", "authenticate"))
        self.assertEqual(auth[3][:3], ("newshop", "admin", "admin"))
        user_write = next(c for c in self.rpc_calls if "res.users" in c[3])
        values = user_write[3][-2][1]
        self.assertEqual(values["login"], self.newcomer.email)
        password = values["password"]
        self.assertGreaterEqual(len(password), 16)
        self.assertEqual(self.patched_hosts, [("newshop", "newshop.clients.example.com")])
        # the password only travels in an auto-deleted e-mail, never in the chatter
        mail = self.env["mail.mail"].sudo().search([("email_to", "ilike", self.newcomer.email)])
        self.assertTrue(mail and all(m.auto_delete for m in mail))
        self.assertIn(password, "".join(mail.mapped("body_html")))
        self.assertFalse(
            any(password in (m.body or "") for m in req.message_ids + prod.message_ids)
        )
        # committed once the access e-mail is queued, before the host and the staging
        self.assertEqual(self.commits, [True])
        staging = req.staging_id
        self.assertEqual(staging.production_instance_id, prod)
        self.assertFalse(staging.herd_agent_allowed)

        staging.phase = "Running"
        self.env["k8s.odoo.instance.request"]._cron_herd_requests()
        self.assertEqual(req.state, "done")
        self.assertFalse(self.env["k8s.odoo.instance.request"]._herd_can_request(self.newcomer))

    @mute_logger("odoo.addons.odoo_herd_portal.models.k8s_odoo_instance_request")
    def test_unsecured_database_stays_unreachable(self):
        req = self._ask()
        req.with_user(self.manager).action_herd_approve()
        self.rpc_uid = False  # admin/admin refused
        req.production_id.phase = "Running"
        self.env["k8s.odoo.instance.request"]._cron_herd_requests()
        self.assertEqual(req.state, "failed")
        self.assertFalse(self.patched_hosts)
        self.assertFalse(req.staging_id)

    @mute_logger("odoo.addons.odoo_herd_portal.models.k8s_odoo_instance_request")
    def test_resume_after_the_commit(self):
        """The host patch fails after the access e-mail commit: the next run
        sets the host and creates the staging, without touching the database
        again."""
        req = self._ask()
        req.with_user(self.manager).action_herd_approve()
        req.production_id.phase = "Running"
        with patch.object(type(req), "_herd_patch_hosts", side_effect=RuntimeError("API down")):
            self.env["k8s.odoo.instance.request"]._cron_herd_requests()
        self.assertEqual(req.state, "cloning")
        self.assertFalse(req.staging_id)
        self.assertEqual(self.commits, [True])
        calls = len(self.rpc_calls)
        self.env["k8s.odoo.instance.request"]._cron_herd_requests()
        self.assertEqual(len(self.rpc_calls), calls)
        self.assertEqual(self.patched_hosts, [("newshop", "newshop.clients.example.com")])
        self.assertTrue(req.staging_id)

    def test_requester_needs_an_email(self):
        self.newcomer.email = False
        with self.assertRaises(UserError):
            self._ask()

    def test_failed_init(self):
        req = self._ask()
        req.with_user(self.manager).action_herd_approve()
        req.production_id.phase = "InitFailed"
        self.env["k8s.odoo.instance.request"]._cron_herd_requests()
        self.assertEqual(req.state, "failed")

    def test_refuse_and_cancel(self):
        req = self._ask()
        with self.assertRaises(AccessError):
            req.with_user(self.newcomer).action_herd_refuse()
        Request = self.env["k8s.odoo.instance.request"]
        with self.assertRaises(AccessError):
            Request.with_user(self.client_user).herd_cancel_database_request(req.id)
        Request.with_user(self.newcomer).herd_cancel_database_request(req.id)
        self.assertEqual(req.state, "cancelled")
        req2 = self._ask(name="newshop2")
        req2.with_user(self.manager).action_herd_refuse()
        self.assertEqual(req2.state, "refused")

    def test_phase_change_wakes_the_cron(self):
        req = self._ask()
        req.with_user(self.manager).action_herd_approve()
        cron = self.env.ref("odoo_herd_portal.cron_herd_requests")
        with patch.object(type(cron), "_trigger") as trigger:
            req.production_id.phase = "Starting"
            self.assertTrue(trigger.called)
        with patch.object(type(cron), "_trigger") as trigger:
            self.staging.phase = "Running"  # unrelated instance
            self.assertFalse(trigger.called)

    def test_wizard_database_name(self):
        wizard = self.env["k8s.create.instance.wizard"].new(
            dict(
                self.offer.get_template_values(),
                cluster_id=self.cluster.id,
                name="newshop",
                namespace="odoo-clients",
                admin_password="x",
                ingress_hosts="newshop.herd-pending.invalid",
                environment="production",
                initialization_mode="fresh",
            )
        )
        spec = wizard.with_context(herd_database_name="newshop")._build_instance_spec(["h"])
        self.assertEqual(spec["database"]["name"], "newshop")
        self.assertNotIn("name", wizard._build_instance_spec(["h"]).get("database", {}))


@tagged("post_install", "-at_install")
class TestHerdRequestPortal(HerdRequestMixin, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._herd_request_setup()

    def setUp(self):
        super().setUp()
        self._request_mocks()

    def _counters(self):
        response = self.url_open(
            "/my/counters",
            data=json.dumps({"params": {"counters": {"herd_instance_count": "service_category"}}}),
            headers={"Content-Type": "application/json"},
        )
        return response.json()["result"]

    def test_newcomer_requests_from_the_portal(self):
        self.authenticate("herd_stranger", "herd_stranger")
        self.assertEqual(self._counters(), {"herd_instance_count": 0})
        page = self.url_open("/my/odoo")
        self.assertIn('href="/my/odoo/new"', page.text)
        page = self.url_open("/my/odoo/new")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Standard", page.text)
        self.assertIn("clients.example.com", page.text)
        response = self.url_open(
            "/my/odoo/new/submit",
            data={
                "csrf_token": self.csrf_token(),
                "template_id": self.offer.id,
                "instance_name": "newshop",
            },
        )
        self.assertEqual(response.status_code, 200)
        req = self.env["k8s.odoo.instance.request"].search([("instance_name", "=", "newshop")])
        self.assertEqual(req.state, "requested")
        page = self.url_open("/my/odoo")
        self.assertIn("newshop.clients.example.com", page.text)
        self.assertNotIn('href="/my/odoo/new"', page.text)
        # the open request keeps the card visible
        self.assertEqual(self._counters(), {"herd_instance_count": 0})

    def test_bad_name_comes_back_with_the_error(self):
        self.authenticate("herd_stranger", "herd_stranger")
        response = self.url_open(
            "/my/odoo/new/submit",
            data={
                "csrf_token": self.csrf_token(),
                "template_id": self.offer.id,
                "instance_name": "x",
            },
        )
        self.assertIn("/my/odoo/new", response.url)
        self.assertIn("alert-danger", response.text)
        self.assertFalse(self.env["k8s.odoo.instance.request"].search([]))

    def test_client_with_a_database_gets_no_offer(self):
        self.authenticate("herd_client_user", "herd_client_user")
        self.assertNotIn('href="/my/odoo/new"', self.url_open("/my/odoo").text)
        self.assertNotIn("/my/odoo/new", self.url_open("/my/odoo/new").url)

    def test_card_hidden_without_offer(self):
        self.offer.herd_portal_published = False
        self.authenticate("herd_stranger", "herd_stranger")
        self.assertEqual(self._counters(), {})

    def test_cannot_cancel_another_clients_request(self):
        req = self._ask()
        self.authenticate("herd_client_user", "herd_client_user")
        self.url_open(f"/my/odoo/request/{req.id}/cancel", data={"csrf_token": self.csrf_token()})
        self.assertEqual(req.state, "requested")
