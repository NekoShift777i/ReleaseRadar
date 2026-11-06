import unittest
from unittest.mock import patch

from check_locks import SoftwareCheckLocks
from main import check_updates


class MainCheckLockTests(unittest.TestCase):
    def test_busy_program_is_skipped_without_database_access(self):
        locks = SoftwareCheckLocks()
        config = {"software": [{
            "id": "xray", "name": "Xray", "enabled": True,
            "current_version": "v1",
        }]}
        skipped = set()
        with locks.reserve("xray") as acquired:
            self.assertTrue(acquired)
            with patch("main.get_or_create_software_state") as get_state, \
                 patch("main.get_latest_release") as get_release, \
                 patch("main.update_software_check") as update_check:
                results = check_updates(config, check_locks=locks, skipped_busy=skipped)
        self.assertEqual(results, [])
        self.assertEqual(skipped, {"xray"})
        get_state.assert_not_called()
        get_release.assert_not_called()
        update_check.assert_not_called()

    def test_other_program_is_not_blocked(self):
        locks = SoftwareCheckLocks()
        config = {"software": [{
            "id": "xray", "name": "Xray", "enabled": True,
            "current_version": "v1",
        }, {
            "id": "nextcloud", "name": "Nextcloud", "enabled": True,
            "current_version": "v1",
        }]}
        skipped = set()
        with locks.reserve("xray"):
            with patch("main.get_or_create_software_state", return_value={"current_version": "v1"}) as get_state, \
                 patch("main.get_latest_release") as get_release, \
                 patch("main.get_software_state", return_value={
                     "current_version": "v1", "last_notified_version": None,
                 }), \
                 patch("main.update_software_check") as update_check:
                get_release.return_value.version = "v1"
                get_release.return_value.url = "https://example.invalid/release"
                results = check_updates(config, check_locks=locks, skipped_busy=skipped)
        self.assertEqual(skipped, {"xray"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].software_id, "nextcloud")
        get_state.assert_called_once()
        update_check.assert_called_once()
