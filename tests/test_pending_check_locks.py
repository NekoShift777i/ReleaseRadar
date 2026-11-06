import unittest
from types import SimpleNamespace
from unittest.mock import patch

from check_locks import SoftwareCheckLocks
from telegram_handlers import get_pending_release


class PendingCheckLocksTests(unittest.TestCase):
    def setUp(self):
        self.locks = SoftwareCheckLocks()
        self.software = {"id": "xray", "name": "Xray", "enabled": True}

    def test_busy_program_does_not_fetch_or_read_state(self):
        with self.locks.reserve("xray"):
            with patch("telegram_handlers.get_latest_release") as fetch, \
                 patch("telegram_handlers.get_software_state") as read:
                result = get_pending_release(self.software, self.locks)
        self.assertIsNone(result)
        fetch.assert_not_called()
        read.assert_not_called()

    def test_available_program_fetches_and_rechecks_state(self):
        release = SimpleNamespace(version="v2", url="https://example.invalid/v2")
        state = {"current_version": "v1", "latest_version": "v2"}
        with patch("telegram_handlers.get_latest_release", return_value=release) as fetch, \
             patch("telegram_handlers.get_software_state", return_value=state) as read:
            result = get_pending_release(self.software, self.locks)
        self.assertEqual(result, (release, state))
        fetch.assert_called_once_with(self.software)
        read.assert_called_once_with("xray")

    def test_version_changed_during_fetch_is_skipped(self):
        release = SimpleNamespace(version="v2")
        state = {"current_version": "v2", "latest_version": "v2"}
        with patch("telegram_handlers.get_latest_release", return_value=release), \
             patch("telegram_handlers.get_software_state", return_value=state):
            self.assertIsNone(get_pending_release(self.software, self.locks))

    def test_reservation_released_after_fetch_failure(self):
        with patch("telegram_handlers.get_latest_release", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                get_pending_release(self.software, self.locks)
        with self.locks.reserve("xray") as acquired:
            self.assertTrue(acquired)
