import threading
import time
import unittest

from parallel_checks import run_parallel_checks


class ParallelExecutorTests(unittest.TestCase):
    def test_preserves_input_order_despite_completion_order(self):
        def worker(value):
            time.sleep((4 - value) * 0.01)
            return value * 10
        self.assertEqual(run_parallel_checks([1, 2, 3], worker, 3), [10, 20, 30])

    def test_concurrency_never_exceeds_limit(self):
        lock = threading.Lock()
        active = peak = 0
        def worker(value):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.025)
            with lock:
                active -= 1
            return value
        self.assertEqual(len(run_parallel_checks(range(10), worker, 4)), 10)
        self.assertEqual(peak, 4)

    def test_one_failure_does_not_stop_others(self):
        errors = []
        def worker(value):
            if value == 2:
                raise RuntimeError("failure")
            return value
        self.assertEqual(run_parallel_checks([1, 2, 3], worker, 2,
                                             on_error=lambda item, error: errors.append((item, str(error)))), [1, 3])
        self.assertEqual(errors, [(2, "failure")])

    def test_stopped_before_start_does_not_execute(self):
        stopped = threading.Event()
        stopped.set()
        self.assertEqual(run_parallel_checks([1], lambda x: self.fail("should not run"), stop_event=stopped), [])

    def test_stop_prevents_queued_work(self):
        stopped = threading.Event()
        started = []
        def worker(value):
            started.append(value)
            stopped.set()
            return value
        self.assertEqual(run_parallel_checks(range(5), worker, 1, stop_event=stopped), [0])
        self.assertEqual(started, [0])

    def test_invalid_limit(self):
        for value in (0, -1, True, 1.5, "4", 17, 10000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                run_parallel_checks([], lambda x: x, value)


if __name__ == "__main__":
    unittest.main()
