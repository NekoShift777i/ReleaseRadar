"""Thread-safe, non-blocking per-software check reservations."""

from contextlib import contextmanager
from threading import Lock
from collections.abc import Iterator


class SoftwareCheckLocks:
    """Prevent overlapping operations for the same software ID."""

    def __init__(self) -> None:
        self._guard = Lock()
        self._busy: set[str] = set()

    @contextmanager
    def reserve(self, software_id: str) -> Iterator[bool]:
        """Yield False if already busy; always release an acquired reservation."""
        with self._guard:
            acquired = software_id not in self._busy
            if acquired:
                self._busy.add(software_id)
        if not acquired:
            yield False
            return
        try:
            yield True
        finally:
            with self._guard:
                self._busy.remove(software_id)
