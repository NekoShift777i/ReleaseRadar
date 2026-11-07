"""Bounded parallel execution of independent software checks."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable, Iterable
from threading import Event
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def run_parallel_checks(
    items: Iterable[T],
    worker: Callable[[T], R],
    max_parallel_checks: int = 4,
    stop_event: Event | None = None,
    on_error: Callable[[T, Exception], None] | None = None,
) -> list[R]:
    """Run up to max_parallel_checks workers; isolate failures and preserve input order.

    The caller owns database synchronization and per-software reservations.
    This executor does not cancel a worker already running when stop is requested.
    """
    if isinstance(max_parallel_checks, bool) or not isinstance(max_parallel_checks, int) or not 1 <= max_parallel_checks <= 16:
        raise ValueError("max_parallel_checks must be an integer between 1 and 16")

    selected = list(items)
    if not selected or (stop_event is not None and stop_event.is_set()):
        return []

    outcomes: dict[int, R] = {}
    with ThreadPoolExecutor(max_workers=max_parallel_checks, thread_name_prefix="release-check") as pool:
        pending = {}
        next_index = 0

        def submit_available() -> None:
            nonlocal next_index
            while len(pending) < max_parallel_checks and next_index < len(selected):
                if stop_event is not None and stop_event.is_set():
                    break
                index = next_index
                next_index += 1
                pending[pool.submit(worker, selected[index])] = index

        submit_available()
        while pending:
            future = next(as_completed(pending))
            index = pending.pop(future)
            try:
                outcomes[index] = future.result()
            except Exception as exc:
                if on_error is not None:
                    on_error(selected[index], exc)
            submit_available()

    return [outcomes[i] for i in sorted(outcomes)]
