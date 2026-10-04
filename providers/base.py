from dataclasses import dataclass
from threading import Event


class CheckCancelled(Exception):
    """Cooperative stop of a synchronous release check."""


def raise_if_stopping(stop_event: Event | None) -> None:
    if stop_event is not None and stop_event.is_set():
        raise CheckCancelled


@dataclass
class Release:
    version: str
    url: str
    prerelease: bool
