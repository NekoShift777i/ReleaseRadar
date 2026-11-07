import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from contextlib import closing

import database as db


class ButtonMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / "test.db"

    def tearDown(self):
        db.DATABASE_PATH = self.old_path
        self.temp.cleanup()

    def test_new_database_stores_creation_time(self):
        db.initialize_database()

        token = db.create_notification_button("xray", "v2")

        with db.get_connection() as connection:
            row = connection.execute(
                "SELECT created_at FROM notification_buttons WHERE token = ?",
                (token,),
            ).fetchone()

        self.assertIsNotNone(row)
        created_at = datetime.fromisoformat(row["created_at"])
        self.assertIsNotNone(created_at.tzinfo)
        self.assertLessEqual(created_at, datetime.now(timezone.utc))

    def test_existing_database_is_migrated_without_data_loss(self):
        with closing(sqlite3.connect(db.DATABASE_PATH)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE notification_buttons (
                        token TEXT PRIMARY KEY,
                        software_id TEXT NOT NULL,
                        version TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO notification_buttons VALUES (?, ?, ?)",
                    ("old-token", "xray", "v2"),
                )

        db.initialize_database()
        db.initialize_database()

        with db.get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM notification_buttons WHERE token = ?",
                ("old-token",),
            ).fetchone()

        self.assertEqual(row["software_id"], "xray")
        self.assertEqual(row["version"], "v2")
        self.assertIsNotNone(row["created_at"])
        self.assertIsNotNone(
            datetime.fromisoformat(row["created_at"]).tzinfo
        )


if __name__ == "__main__":
    unittest.main()