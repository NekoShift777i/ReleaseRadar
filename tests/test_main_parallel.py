import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from main import check_updates


class MainParallelTests(unittest.TestCase):
    def setUp(self):
        self.config = {"max_parallel_checks": 2, "software": [
            {"id": str(i), "name": f"Program {i}", "enabled": True, "current_version": "v1"}
            for i in range(4)
        ]}

    def test_network_concurrency_and_serial_database(self):
        guard = threading.Lock()
        active = peak = 0
        database_threads = []
        main_thread = threading.get_ident()

        def fetch(software, stop_event=None):
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(0.03)
            with guard:
                active -= 1
            return SimpleNamespace(version="v2", url="https://example.invalid")

        def db_state(*args):
            database_threads.append(threading.get_ident())
            return {"current_version": "v1", "last_notified_version": None}


        with patch("main.get_latest_release", side_effect=fetch), \
             patch("main.get_or_create_software_state", side_effect=db_state), \
             patch("main.get_software_state", side_effect=db_state), \
             patch("main.is_release_skipped", return_value=False), \
             patch(
                 "main.update_software_check",
                 side_effect=lambda *args: database_threads.append(
                     threading.get_ident()
                 ),
             ):
            results = check_updates(self.config)

        self.assertEqual(peak, 2)
        self.assertEqual([r.software_id for r in results], ["0", "1", "2", "3"])
        self.assertTrue(database_threads)
        self.assertTrue(all(t == main_thread for t in database_threads))

    def test_failed_fetch_does_not_block_others(self):
        def fetch(software, stop_event=None):
            if software["id"] == "1":
                raise RuntimeError("simulated failure")
            return SimpleNamespace(version="v1", url="https://example.invalid")

        state = {"current_version": "v1", "last_notified_version": None}
        with patch("main.get_latest_release", side_effect=fetch), \
             patch("main.get_or_create_software_state", return_value=state), \
             patch("main.get_software_state", return_value=state), \
             patch("main.update_software_check"), \
             patch("main.record_software_error") as record_error:
            results = check_updates(self.config)
        self.assertEqual([r.software_id for r in results], ["0", "2", "3"])
        record_error.assert_called_once()
        self.assertEqual(record_error.call_args.args[0], "1")
