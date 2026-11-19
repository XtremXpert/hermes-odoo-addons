# Copyright 2026 XtremXpert
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import base64

from odoo.tests import TransactionCase


class TestDmsFileVersions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.storage = cls.env["dms.storage"].create(
            {"name": "Versions test storage", "save_type": "database"}
        )
        cls.access_group = cls.env["dms.access.group"].create(
            {
                "name": "Versions test group",
                "perm_create": True,
                "perm_write": True,
                "perm_unlink": True,
            }
        )
        cls.directory = cls.env["dms.directory"].create(
            {
                "name": "Versions test directory",
                "storage_id": cls.storage.id,
                "is_root_directory": True,
                "group_ids": [(4, cls.access_group.id)],
            }
        )
        cls.file = cls.env["dms.file"].create(
            {
                "name": "versioned.txt",
                "directory_id": cls.directory.id,
                "content": cls._b64(b"version 1"),
            }
        )

    @staticmethod
    def _b64(data):
        return base64.b64encode(data).decode()

    def test_content_update_archives_the_previous_content(self):
        """Replacing the content archives the outgoing bytes, not the new ones.

        Odoo 20 only accepts a BinaryValue in a binary field: raw ``bytes``
        raise "use BinaryValue instead of bytes" and break every write.
        """
        self.file.write({"content": self._b64(b"version 2")})
        self.assertEqual(self.file.version_count, 1)
        version = self.file.version_ids
        self.assertEqual(bytes(version.content), b"version 1")
        self.assertEqual(version.origin, "update")

    def test_restore_writes_the_version_back(self):
        self.file.write({"content": self._b64(b"version 2")})
        version = self.file.version_ids
        version.action_restore()
        self.assertEqual(bytes(self.file.content), b"version 1")
        # The content replaced by the restore is archived too, and keeps the
        # bytes that were live before the restore.
        self.assertEqual(self.file.version_count, 2)
        self.assertEqual(sorted(self.file.version_ids.mapped("origin")), ["restore", "update"])
        restore_version = self.file.version_ids.filtered(
            lambda version: version.origin == "restore"
        )
        self.assertEqual(bytes(restore_version.content), b"version 2")
