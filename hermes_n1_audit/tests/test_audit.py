from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestAudit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Prépare l'agent, l'administrateur et le contact utilisés par les tests."""
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.bot = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "N1 test bot",
                    "login": "n1_audit_test_bot",
                    "group_ids": [
                        (
                            6,
                            0,
                            [
                                cls.env.ref("base.group_user").id,
                                cls.env.ref("hermes_n1_audit.group_agent").id,
                            ],
                        )
                    ],
                }
            )
        )
        cls.channel = (
            cls.env["discuss.channel"]
            .with_user(cls.admin)
            ._get_or_create_chat([cls.bot.partner_id.id])
        )
        cls.message = cls.channel.with_user(cls.admin).message_post(
            body="Modifier la ville du contact technique.",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        cls.contact = cls.env["res.partner"].create({"name": "N1 Audit Fixture", "city": "Avant"})
        cls.service = cls.env["hermes.n1.change"].with_user(cls.bot)

    def arguments(self, **extra):
        """Construit les arguments d'un appel `modifier` de référence."""
        return dict(
            {
                "model": "res.partner",
                "record_id": self.contact.id,
                "values": {"city": "Après"},
                "expected": {"city": "Avant"},
                "reason": "Correction demandée <script>test</script>",
                "channel_id": self.channel.id,
                "message_id": self.message.id,
                "partner_id": self.admin.partner_id.id,
            },
            **extra,
        )

    def test_write_and_note_are_atomic_and_attributed(self):
        """Vérifie que l'écriture et sa note sont atomiques et attribuées."""
        result = self.service.modifier(**self.arguments())
        self.assertEqual(self.contact.city, "Après")
        note = self.env["mail.message"].browse(result["chatter_message_id"])
        self.assertEqual((note.model, note.res_id), ("res.partner", self.contact.id))
        self.assertEqual(note.author_id, self.bot.partner_id)
        self.assertIn("Avant", note.body)
        self.assertIn("Après", note.body)
        self.assertIn(str(self.message.id), note.body)
        self.assertIn("&lt;script&gt;", note.body)
        self.assertNotIn("<script>", note.body)

    def test_chatter_failure_rolls_back_even_when_caught(self):
        """Vérifie que l'échec du chatter annule tout, même quand l'erreur est interceptée."""
        with patch.object(
            type(self.contact), "message_post", side_effect=UserError("No chatter")
        ) as post:
            with self.assertRaises(UserError):
                self.service.modifier(**self.arguments())
            post.assert_called_once()
        self.contact.invalidate_recordset()
        self.assertEqual(self.contact.city, "Avant")
        self.assertFalse(
            self.env["hermes.n1.change"].search([("source_message_id", "=", self.message.id)])
        )

    def test_replay_does_not_write_or_post_twice(self):
        """Vérifie qu'un rejeu ne réécrit pas et ne reposte pas."""
        first = self.service.modifier(**self.arguments())
        second = self.service.modifier(**self.arguments())
        self.assertEqual(first["audit_id"], second["audit_id"])
        self.assertEqual(first["chatter_message_id"], second["chatter_message_id"])
        self.assertTrue(second["deja_applique"])

    def test_stale_values_and_forbidden_fields_leave_object_unchanged(self):
        """Vérifie qu'un conflit de valeurs ou un champ interdit laisse l'objet intact."""
        for changes in [
            {"expected": {"city": "Stale"}},
            {"values": {"user_id": self.admin.id}, "expected": {"user_id": False}},
            {"reason": ""},
        ]:
            with self.assertRaises(UserError):
                self.service.modifier(**self.arguments(**changes))
        self.assertEqual(self.contact.city, "Avant")

    def test_untrusted_caller_and_forged_source_are_denied(self):
        """Vérifie qu'un appelant non agent ou une source forgée est refusé."""
        with self.assertRaises(AccessError):
            self.env["hermes.n1.change"].with_user(self.admin).modifier(**self.arguments())
        with self.assertRaises(AccessError):
            self.service.modifier(**self.arguments(partner_id=self.bot.partner_id.id))
        with self.assertRaises(AccessError):
            self.service.modifier(**self.arguments(channel_id=0))

    def test_audit_is_immutable(self):
        """Vérifie que le journal refuse toute écriture et toute suppression."""
        result = self.service.modifier(**self.arguments())
        audit = self.env["hermes.n1.change"].browse(result["audit_id"])
        with self.assertRaises(AccessError):
            audit.write({"reason": "tampered"})
        with self.assertRaises(AccessError):
            audit.unlink()

    def test_no_chatter_or_model_outside_policy_is_not_editable(self):
        """Vérifie qu'un modèle hors politique ou sans chatter n'est pas modifiable."""
        self.assertEqual(self.service.capabilities("res.users")["modifiable"], [])
        self.assertIn("city", self.service.capabilities("res.partner")["modifiable"])
        from ..models.change import WRITE_FIELDS

        with patch.dict(WRITE_FIELDS, {"res.country": {"name"}}):
            self.assertEqual(self.service.capabilities("res.country")["modifiable"], [])

    def business_source(self):
        """Construit le contexte Discuss d'un appel à la façade métier."""
        return {
            key: value
            for key, value in self.arguments().items()
            if key in {"channel_id", "message_id", "partner_id"}
        }

    def test_business_discovery_rejects_technical_models(self):
        """Vérifie que la façade métier refuse les modèles techniques."""
        for model in ["ir.config_parameter", "hermes.n3.operation"]:
            with self.assertRaises(AccessError):
                self.service.explorer(model=model, **self.business_source())
        # res.users is readable now: N1 follows the requester's read rights.
        info = self.service.explorer(model="res.users", **self.business_source())
        self.assertEqual(info["editable"], {})
        info = self.service.explorer(model="res.partner", **self.business_source())
        self.assertIn("city", info["editable"])
        self.assertIn("active", info["editable"])
        self.assertIn("user_id", info["editable"])

    def test_website_page_markup_is_editable_without_exposing_views(self):
        """Vérifie que l'arch d'une page site est modifiable sans exposer les vues."""
        if "website.page" not in self.env:
            self.skipTest("website is not installed")
        page_info = self.service.explorer(model="website.page", **self.business_source())
        self.assertIn("arch", page_info["fields"])
        self.assertIn("arch", page_info["editable"])
        with self.assertRaises(AccessError):
            self.service.explorer(model="ir.ui.view", **self.business_source())

    def test_business_create_is_audited_and_idempotent(self):
        """Vérifie qu'une création métier est tracée et rejouable."""
        args = dict(
            model="res.partner",
            values={"name": "Création métier N1"},
            reason="Demande de création",
            **self.business_source(),
        )
        first = self.service.corriger_metier(**args)
        second = self.service.corriger_metier(**args)
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["deja_applique"])
        self.assertTrue(first["chatter_message_id"])

    def test_business_without_chatter_has_central_audit(self):
        """Vérifie qu'un objet sans chatter est tracé dans le journal central."""
        country = self.env["res.country"].create({"name": "Pays test N1", "code": "XZ"})
        result = self.service.corriger_metier(
            model="res.country",
            record_id=country.id,
            values={"name": "Pays corrigé"},
            expected={"name": "Pays test N1"},
            reason="Correction",
            **self.business_source(),
        )
        self.assertEqual(country.name, "Pays corrigé")
        note = self.env["mail.message"].browse(result["chatter_message_id"])
        self.assertEqual(note.model, "hermes.n1.change")

    def test_business_read_blocks_nested_filters_and_hidden_fields(self):
        """Vérifie que la lecture refuse les filtres imbriqués et les champs masqués."""
        for domain in [[["user_ids.password", "=", "x"]], [["name", "any", []]]]:
            with self.assertRaises(UserError):
                self.service.lire_metier(
                    model="res.partner", domain=domain, **self.business_source()
                )
        with self.assertRaises(UserError):
            self.service.corriger_metier(
                model="res.partner",
                record_id=self.contact.id,
                values={"company_id": False},
                expected={"company_id": False},
                reason="Technique",
                **self.business_source(),
            )

    def test_business_write_rolls_back_if_journal_fails(self):
        """Vérifie que l'échec du journal annule l'écriture métier."""
        with patch.object(
            type(self.contact), "message_post", side_effect=UserError("Journal indisponible")
        ):
            with self.assertRaises(UserError):
                self.service.corriger_metier(
                    model="res.partner",
                    record_id=self.contact.id,
                    values={"city": "Après"},
                    expected={"city": "Avant"},
                    reason="Correction",
                    **self.business_source(),
                )
        self.contact.invalidate_recordset()
        self.assertEqual(self.contact.city, "Avant")

    def test_business_rejects_untrusted_source(self):
        """Vérifie que la façade métier refuse une source non fiable."""
        with self.assertRaises(AccessError):
            self.service.lire_metier(
                model="res.partner",
                **dict(self.business_source(), partner_id=self.bot.partner_id.id),
            )

    def test_project_html_and_task_assignment_use_requester_rights(self):
        """Vérifie que le HTML projet et l'affectation suivent les droits du demandeur."""
        if "project.project" not in self.env:
            self.skipTest("project is not installed")
        info = self.service.explorer(model="project.project", **self.business_source())
        self.assertIn("description", info["editable"])
        project = self.service.corriger_metier(
            model="project.project",
            values={"name": "Projet métier N1", "description": "<p>Objectif commun</p>"},
            reason="Créer le projet demandé",
            **self.business_source(),
        )
        rows = self.service.lire_metier(
            model="project.project",
            domain=[["id", "=", project["id"]]],
            names=["id", "description"],
            **self.business_source(),
        )["rows"]
        self.assertIn("Objectif commun", rows[0]["description"])
        result = self.service.corriger_metier(
            model="project.project",
            record_id=project["id"],
            values={"description": "<p>Objectif précisé</p>"},
            expected={"description": rows[0]["description"]},
            reason="Corédiger",
            **self.business_source(),
        )
        self.assertTrue(result["audit_id"])
        task = self.service.corriger_metier(
            model="project.task",
            values={
                "name": "Tâche N1",
                "project_id": project["id"],
                "user_ids": [[6, 0, [self.admin.id]]],
            },
            reason="Affectation demandée",
            **self.business_source(),
        )
        self.assertEqual(self.env["project.task"].browse(task["id"]).user_ids, self.admin)
        with self.assertRaises(UserError):
            self.service.corriger_metier(
                model="project.task",
                record_id=task["id"],
                values={"user_ids": [[1, self.admin.id, {"name": "Interdit"}]]},
                expected={"user_ids": [self.admin.id]},
                reason="Injection",
                **self.business_source(),
            )

    def test_archive_and_delete_are_audited_and_replayable(self):
        """Vérifie que l'archivage et la suppression sont tracés et rejouables."""
        row = self.service.lire_metier(
            model="res.partner",
            domain=[["id", "=", self.contact.id]],
            names=["write_date", "active"],
            **self.business_source(),
        )["rows"][0]
        row.pop("id", None)
        args = dict(
            model="res.partner",
            record_id=self.contact.id,
            action="archive",
            expected=row,
            reason="Archiver le contact test",
            **self.business_source(),
        )
        first = self.service.agir_metier(**args)
        second = self.service.agir_metier(**args)
        self.assertFalse(self.contact.active)
        self.assertEqual(first["audit_id"], second["audit_id"])
        self.assertTrue(second["deja_applique"])
        country = self.env["res.country"].create({"name": "Pays supprimable N1", "code": "XZ"})
        expected = country.read(["name", "write_date"], load=None)[0]
        expected.pop("id")
        args = dict(
            model="res.country",
            record_id=country.id,
            action="unlink",
            expected=expected,
            reason="Supprimer cette fixture",
            **self.business_source(),
        )
        result = self.service.agir_metier(**args)
        self.assertFalse(country.exists())
        note = self.env["mail.message"].browse(result["chatter_message_id"])
        self.assertEqual(note.model, "hermes.n1.change")
        self.assertEqual(result["audit_id"], self.service.agir_metier(**args)["audit_id"])

    def test_actions_reject_stale_values_arbitrary_methods_and_technical_models(self):
        """Vérifie que les actions refusent valeurs périmées et méthodes arbitraires."""
        args = dict(
            model="res.partner",
            record_id=self.contact.id,
            action="archive",
            expected={"write_date": False},
            reason="Test",
            **self.business_source(),
        )
        with self.assertRaises(UserError):
            self.service.agir_metier(**args)
        for action in ("sudo", "message_post", "action_reset_password", "write"):
            with self.assertRaises(UserError):
                self.service.agir_metier(**dict(args, action=action))
        for model in ("k8s.odoo.instance", "ir.config_parameter"):
            with self.assertRaises(AccessError):
                self.service.explorer(model=model, **self.business_source())
        self.assertTrue(self.contact.active)

    def test_requester_acl_is_used_without_elevating_business_operations(self):
        """Vérifie que l'ACL du demandeur s'applique sans élever les droits."""
        # The real source verifier is covered above. A restricted actor here proves
        # the operation itself cannot inherit the bot/admin's permissions.
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "N1 restricted fixture",
                    "login": "n1_restricted_fixture",
                    "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
                }
            )
        )
        with patch.object(type(self.service), "_business_actor", return_value=(user, self.message)):
            with self.assertRaises(AccessError):
                self.service.corriger_metier(
                    model="res.country",
                    values={"name": "Forbidden", "code": "XZ"},
                    reason="Test droits",
                    **self.business_source(),
                )

    def test_delete_rolls_back_when_journal_is_unavailable(self):
        """Vérifie que la suppression est annulée si le journal est indisponible."""
        country = self.env["res.country"].create({"name": "Pays protégé N1", "code": "XZ"})
        expected = country.read(["write_date"], load=None)[0]
        expected.pop("id")
        with patch.object(
            type(self.service), "message_post", side_effect=UserError("Journal indisponible")
        ):
            with self.assertRaises(UserError):
                self.service.agir_metier(
                    model="res.country",
                    record_id=country.id,
                    action="unlink",
                    expected=expected,
                    reason="Test atomique",
                    **self.business_source(),
                )
        self.assertTrue(country.exists())

    def test_action_detects_another_write_within_the_same_second(self):
        """Vérifie que l'action détecte une autre écriture dans la même seconde."""
        expected = self.service.lire_metier(
            model="res.partner",
            domain=[["id", "=", self.contact.id]],
            names=["write_date"],
            **self.business_source(),
        )["rows"][0]
        expected.pop("id")
        self.env.cr.execute(
            "UPDATE res_partner SET write_date = write_date + interval '1 microsecond' WHERE id = %s",
            [self.contact.id],
        )
        self.contact.invalidate_recordset()
        with self.assertRaises(UserError):
            self.service.agir_metier(
                model="res.partner",
                record_id=self.contact.id,
                action="archive",
                expected=expected,
                reason="Test concurrence",
                **self.business_source(),
            )
        self.assertTrue(self.contact.active)

    def test_delete_previously_audited_chatter_preserves_original_note(self):
        """Vérifie que la suppression d'un chatter déjà audité conserve la note d'origine."""
        changed = self.service.corriger_metier(
            model="res.partner",
            record_id=self.contact.id,
            values={"city": "Après"},
            expected={"city": "Avant"},
            reason="Correction avant suppression",
            **self.business_source(),
        )
        audit = self.env["hermes.n1.change"].browse(changed["audit_id"])
        original = audit.read(["chatter_message_id", "before_values", "after_values", "reason"])[0]
        note = audit.chatter_message_id
        body = note.body
        expected = self.service.lire_metier(
            model="res.partner",
            domain=[["id", "=", self.contact.id]],
            names=["write_date", "name"],
            **self.business_source(),
        )["rows"][0]
        expected.pop("id")
        deleted = self.service.agir_metier(
            model="res.partner",
            record_id=self.contact.id,
            action="unlink",
            expected=expected,
            reason="Supprimer cette fixture",
            **self.business_source(),
        )
        self.assertFalse(self.contact.exists())
        self.assertTrue(note.exists())
        self.assertEqual(note.body, body)
        self.assertEqual((note.model, note.res_id), ("hermes.n1.change", audit.id))
        self.assertEqual(
            original,
            audit.read(["chatter_message_id", "before_values", "after_values", "reason"])[0],
        )
        self.assertNotEqual(deleted["chatter_message_id"], note.id)
        with self.assertRaises(AccessError):
            note.unlink()

    def test_project_cascade_preserves_child_audit_note(self):
        """Vérifie que la cascade projet conserve la note d'audit de l'enfant."""
        if "project.project" not in self.env:
            self.skipTest("project is not installed")
        project = self.env["project.project"].create({"name": "Cascade audit N1"})
        result = self.service.corriger_metier(
            model="project.task",
            values={"name": "Enfant audité", "project_id": project.id},
            reason="Test cascade",
            **self.business_source(),
        )
        audit = self.env["hermes.n1.change"].browse(result["audit_id"])
        note = audit.chatter_message_id
        project.unlink()  # Normal UI/ORM deletion must preserve the journal too.
        self.assertFalse(self.env["project.task"].browse(result["id"]).exists())
        self.assertTrue(note.exists())
        self.assertEqual((note.model, note.res_id), ("hermes.n1.change", audit.id))

    def test_denied_message_delete_cannot_move_the_audit_note(self):
        """Vérifie qu'une suppression refusée ne déplace pas la note d'audit."""
        changed = self.service.modifier(**self.arguments())
        note = self.env["mail.message"].browse(changed["chatter_message_id"])
        with patch.object(type(note), "check_access", side_effect=AccessError("Denied")):
            with self.assertRaises(AccessError):
                note.unlink()
        self.assertEqual((note.model, note.res_id), ("res.partner", self.contact.id))

    def test_failed_delete_journal_rolls_back_note_reparenting(self):
        """Vérifie que l'échec du journal annule le déplacement de la note."""
        changed = self.service.modifier(**self.arguments())
        note = self.env["mail.message"].browse(changed["chatter_message_id"])
        expected = self.service.lire_metier(
            model="res.partner",
            domain=[["id", "=", self.contact.id]],
            names=["write_date"],
            **self.business_source(),
        )["rows"][0]
        expected.pop("id")
        with patch.object(
            type(self.service), "message_post", side_effect=UserError("Journal indisponible")
        ):
            with self.assertRaises(UserError):
                self.service.agir_metier(
                    model="res.partner",
                    record_id=self.contact.id,
                    action="unlink",
                    expected=expected,
                    reason="Test atomique",
                    **self.business_source(),
                )
        self.assertTrue(self.contact.exists())
        note.invalidate_recordset()
        self.assertEqual((note.model, note.res_id), ("res.partner", self.contact.id))
