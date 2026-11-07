
import tempfile
import unittest
from pathlib import Path

import database as db


class SkippedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / "test.db"
        db.initialize_database()
        db.create_software_state("xray", "v1.0")
        db.update_software_check(
            "xray",
            "v2.0",
            "2026-11-07T00:00:00+00:00",
        )

    def tearDown(self):
        db.DATABASE_PATH = self.old_path
        self.temp.cleanup()

    def test_skip_release(self):
        result = db.skip_release(
            "xray",
            "v2.0",
            "Пока не требуется",
        )

        self.assertTrue(result)
        self.assertTrue(
            db.is_release_skipped("xray", "v2.0")
        )
        self.assertFalse(
            db.is_release_skipped("xray", "v2.1")
        )

    def test_duplicate_skip_preserves_reason(self):
        self.assertTrue(
            db.skip_release("xray", "v2.0", "Первая причина")
        )
        self.assertFalse(
            db.skip_release("xray", "v2.0", "Вторая причина")
        )

        with db.get_connection() as connection:
            row = connection.execute(
                """
                SELECT reason FROM skipped_releases
                WHERE software_id = ? AND version = ?
                """,
                ("xray", "v2.0"),
            ).fetchone()

        self.assertEqual(row["reason"], "Первая причина")

    def test_skip_is_specific_to_software(self):
        db.skip_release("xray", "v2.0", "Не требуется")

        self.assertFalse(
            db.is_release_skipped("nextcloud", "v2.0")
        )

    def test_empty_reason_is_rejected(self):
        with self.assertRaises(ValueError):
            db.skip_release("xray", "v2.0", "   ")

    
    def test_skip_survives_database_initialization(self):
        reason = "Отложено до проверки совместимости"

        self.assertTrue(
            db.skip_release("xray", "v2.0", reason)
        )

        with db.get_connection() as connection:
            before = connection.execute(
                """
                SELECT software_id, version, reason, skipped_at
                FROM skipped_releases
                WHERE software_id = ? AND version = ?
                """,
                ("xray", "v2.0"),
            ).fetchone()

        self.assertIsNotNone(before)

        db.initialize_database()

        with db.get_connection() as connection:
            after = connection.execute(
                """
                SELECT software_id, version, reason, skipped_at
                FROM skipped_releases
                WHERE software_id = ? AND version = ?
                """,
                ("xray", "v2.0"),
            ).fetchone()

        self.assertIsNotNone(after)
        self.assertEqual(dict(before), dict(after))
        self.assertEqual(after["reason"], reason)

        state = db.get_software_state("xray")
        self.assertEqual(state["current_version"], "v1.0")
        self.assertTrue(db.is_release_skipped("xray", "v2.0"))


    def test_installed_version_cannot_be_skipped(self):
        self.assertTrue(
            db.mark_version_updated("xray", "v2.0")
        )

        self.assertFalse(
            db.skip_release("xray", "v2.0", "Уже установлена")
        )

        self.assertFalse(
            db.is_release_skipped("xray", "v2.0")
        )

    def test_outdated_release_cannot_be_skipped(self):
        db.update_software_check(
            "xray",
            "v2.1",
            "2026-11-07T01:00:00+00:00",
        )

        self.assertFalse(
            db.skip_release("xray", "v2.0", "Устаревший выпуск")
        )

    
    def test_get_skipped_releases_history(self):
        self.assertTrue(
            db.skip_release(
                "xray",
                "v2.0",
                "Ожидание исправлений",
            )
        )

        history = db.get_skipped_releases()

        self.assertEqual(len(history), 1)

        record = history[0]

        self.assertEqual(record["software_id"], "xray")
        self.assertEqual(record["version"], "v2.0")
        self.assertEqual(record["reason"], "Ожидание исправлений")
        self.assertIsNotNone(record["skipped_at"])

        # Фильтрация по программе.
        filtered = db.get_skipped_releases("xray")
        self.assertEqual(len(filtered), 1)

        # Для неизвестной программы записей нет.
        self.assertEqual(
            db.get_skipped_releases("unknown"),
            [],
        )

