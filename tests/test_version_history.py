import tempfile
import unittest
import sqlite3
from pathlib import Path

import database as db


class VersionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / "test.db"

    def tearDown(self):
        db.DATABASE_PATH = self.old_path
        self.temp.cleanup()

    def test_version_history_table_created(self):
        db.initialize_database()

        with db.get_connection() as connection:
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(version_change_history)"
                )
            }

        self.assertEqual(
            columns,
            {
                "id",
                "software_id",
                "old_version",
                "new_version",
                "changed_at",
                "source",
            },
        )

    def test_successful_confirmation_creates_history(self):
        db.initialize_database()
        db.create_software_state("xray", "v1")
        db.update_software_check("xray", "v2", "now")

        result = db.mark_version_updated(
            "xray",
            "v2",
            source="test",
        )

        self.assertTrue(result)

        with db.get_connection() as connection:
            rows = connection.execute(
                """
                SELECT software_id, old_version,
                       new_version, changed_at, source
                FROM version_change_history
                """
            ).fetchall()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["software_id"], "xray")
        self.assertEqual(rows[0]["old_version"], "v1")
        self.assertEqual(rows[0]["new_version"], "v2")
        self.assertEqual(rows[0]["source"], "test")
        self.assertTrue(rows[0]["changed_at"])

    def test_duplicate_confirmation_does_not_create_history(self):
        db.initialize_database()
        db.create_software_state("xray", "v1")
        db.update_software_check("xray", "v2", "now")

        self.assertTrue(db.mark_version_updated("xray", "v2"))
        self.assertFalse(db.mark_version_updated("xray", "v2"))

        with db.get_connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM version_change_history"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_history_failure_rolls_back_version(self):
        db.initialize_database()
        db.create_software_state("xray", "v1")
        db.update_software_check("xray", "v2", "now")

        with db.get_connection() as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_version_history
                BEFORE INSERT ON version_change_history
                BEGIN
                    SELECT RAISE(ABORT, 'History write failed');
                END
                """
            )

        with self.assertRaises(sqlite3.IntegrityError):
            db.mark_version_updated(
                "xray",
                "v2",
                source="test",
            )

        with db.get_connection() as connection:
            state = connection.execute(
                """
                SELECT current_version
                FROM software_state
                WHERE software_id = ?
                """,
                ("xray",),
            ).fetchone()

            history_count = connection.execute(
                "SELECT COUNT(*) FROM version_change_history"
            ).fetchone()[0]

        self.assertEqual(state["current_version"], "v1")
        self.assertEqual(history_count, 0)

