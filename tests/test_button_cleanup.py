import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import database as db


class ButtonCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / "test.db"
        db.initialize_database()

    def tearDown(self):
        db.DATABASE_PATH = self.old_path
        self.temp.cleanup()

    def test_removes_only_expired_buttons(self):
        now = datetime(2026, 11, 7, tzinfo=timezone.utc)

        with db.get_connection() as connection:
            for token, age in (
                ("expired", 31),
                ("active", 29),
                ("boundary", 30),
            ):
                connection.execute(
                    """
                    INSERT INTO notification_buttons
                    (token, software_id, version, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        token,
                        "xray",
                        "v2",
                        (now - timedelta(days=age)).isoformat(),
                    ),
                )

        deleted = db.cleanup_notification_buttons(
            timedelta(days=30),
            now=now,
        )

        self.assertEqual(deleted, 1)
        self.assertIsNone(db.get_notification_button("expired"))
        self.assertIsNotNone(db.get_notification_button("active"))
        self.assertIsNotNone(db.get_notification_button("boundary"))

    def test_cleanup_is_repeatable(self):
        now = datetime(2026, 11, 7, tzinfo=timezone.utc)

        self.assertEqual(
            db.cleanup_notification_buttons(timedelta(days=30), now),
            0,
        )
        self.assertEqual(
            db.cleanup_notification_buttons(timedelta(days=30), now),
            0,
        )

    def test_rejects_invalid_retention(self):
        with self.assertRaises(ValueError):
            db.cleanup_notification_buttons(timedelta(0))

    
    def test_button_expiration(self):
        now = datetime(2026, 11, 7, tzinfo=timezone.utc)

        with db.get_connection() as connection:
            for token, age in (
                ("expired", 31),
                ("active", 29),
                ("boundary", 30),
            ):
                connection.execute(
                    """
                    INSERT INTO notification_buttons
                    (token, software_id, version, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        token,
                        "xray",
                        "v2",
                        (now - timedelta(days=age)).isoformat(),
                    ),
                )

        for token in ("expired", "boundary"):
            with self.subTest(token=token):
                self.assertIsNone(
                    db.get_valid_notification_button(
                        token,
                        timedelta(days=30),
                        now,
                    )
                )

        self.assertIsNotNone(
            db.get_valid_notification_button(
                "active",
                timedelta(days=30),
                now,
            )
        )

        self.assertIsNone(
            db.get_valid_notification_button(
                "missing",
                timedelta(days=30),
                now,
            )
        )



if __name__ == "__main__":
    unittest.main()
