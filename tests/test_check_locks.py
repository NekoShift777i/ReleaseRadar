import unittest
from threading import Event, Thread

from check_locks import SoftwareCheckLocks


class SoftwareCheckLocksTests(unittest.TestCase):
    def test_same_program_is_busy_and_other_program_is_available(self):
        locks = SoftwareCheckLocks()
        with locks.reserve("xray") as acquired:
            self.assertTrue(acquired)
            with locks.reserve("xray") as duplicate:
                self.assertFalse(duplicate)
            with locks.reserve("nextcloud") as independent:
                self.assertTrue(independent)
        with locks.reserve("xray") as acquired_again:
            self.assertTrue(acquired_again)

    def test_reservation_released_after_exception(self):
        locks = SoftwareCheckLocks()
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with locks.reserve("xray") as acquired:
                self.assertTrue(acquired)
                raise RuntimeError("test failure")
        with locks.reserve("xray") as acquired_again:
            self.assertTrue(acquired_again)

    def test_reservation_is_shared_across_threads(self):
        locks = SoftwareCheckLocks()
        entered = Event()
        release = Event()
        observed = []

        def worker():
            with locks.reserve("xray") as acquired:
                observed.append(acquired)
                entered.set()
                release.wait(timeout=3)

        thread = Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(entered.wait(timeout=3))
            with locks.reserve("xray") as duplicate:
                self.assertFalse(duplicate)
        finally:
            release.set()
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(observed, [True])
