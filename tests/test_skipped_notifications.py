
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from main import check_updates


class SkippedNotificationTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "max_parallel_checks": 1,
            "software": [
                {
                    "id": "xray",
                    "name": "Xray",
                    "enabled": True,
                    "current_version": "v1.0",
                }
            ],
        }

        self.state = {
            "current_version": "v1.0",
            "last_notified_version": None,
        }

    def check_version(self, version, skipped=False):
        release = SimpleNamespace(
            version=version,
            url="https://example.invalid/release",
        )

        with (
            patch("main.get_latest_release", return_value=release),
            patch(
                "main.get_or_create_software_state",
                return_value=self.state,
            ),
            patch(
                "main.get_software_state",
                return_value=self.state,
            ),
            patch("main.update_software_check"),
            patch(
                "main.is_release_skipped",
                return_value=skipped,
            ),
        ):
            return check_updates(self.config)

    def test_skipped_version_does_not_notify(self):
        results = self.check_version("v2.0", skipped=True)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].update_available)
        self.assertFalse(results[0].notify_required)

    def test_next_version_can_notify(self):
        skipped_results = self.check_version(
            "v2.0",
            skipped=True,
        )
        next_results = self.check_version(
            "v2.1",
            skipped=False,
        )

        self.assertFalse(skipped_results[0].notify_required)
        self.assertTrue(next_results[0].notify_required)
        self.assertEqual(
            next_results[0].current_version,
            "v1.0",
        )


class SkippedReleaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        import database as db

        self.db = db
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH

        db.DATABASE_PATH = Path(self.temp.name) / "test.db"
        db.initialize_database()

        self.config = {
            "max_parallel_checks": 1,
            "software": [
                {
                    "id": "xray",
                    "name": "Xray",
                    "enabled": True,
                    "current_version": "v1.0",
                }
            ],
        }

    def tearDown(self):
        self.db.DATABASE_PATH = self.old_path
        self.temp.cleanup()

    def test_next_release_after_skipped_version(self):
        def check_version(version):
            release = SimpleNamespace(
                version=version,
                url="https://example.invalid/release",
            )

            with patch(
                "main.get_latest_release",
                return_value=release,
            ):
                return check_updates(self.config)

        # Обнаруживаем первый выпуск.
        first = check_version("v2.0")

        self.assertEqual(len(first), 1)
        self.assertTrue(first[0].notify_required)

        # Пользователь пропускает v2.0.
        self.assertTrue(
            self.db.skip_release(
                "xray",
                "v2.0",
                "Отложено до следующего выпуска",
            )
        )

        # Повторная проверка не должна уведомлять о v2.0.
        repeated = check_version("v2.0")

        self.assertEqual(len(repeated), 1)
        self.assertFalse(repeated[0].notify_required)

        # Появляется следующий выпуск.
        next_release = check_version("v2.1")

        self.assertEqual(len(next_release), 1)
        self.assertTrue(next_release[0].update_available)
        self.assertTrue(next_release[0].notify_required)

        # Установленная версия не изменилась.
        state = self.db.get_software_state("xray")

        self.assertEqual(state["current_version"], "v1.0")
        self.assertEqual(state["latest_version"], "v2.1")

        # Пропуск предыдущего выпуска сохранён.
        self.assertTrue(
            self.db.is_release_skipped("xray", "v2.0")
        )
        self.assertFalse(
            self.db.is_release_skipped("xray", "v2.1")
        )
