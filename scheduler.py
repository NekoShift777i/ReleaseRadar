import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


def get_check_interval(config: dict) -> int:
    interval = config.get("check_interval_seconds", 3600)
    if isinstance(interval, bool) or not isinstance(interval, int) or interval <= 0:
        raise ValueError("check_interval_seconds must be a positive integer")
    return interval


async def run_periodic_checks(
    check_once: Callable[[], Awaitable[None]],
    stop_event: asyncio.Event,
    interval: int,
) -> None:
    """Run immediately, then wait after each completed cycle. Never overlap."""
    while not stop_event.is_set():
        try:
            await check_once()
        except Exception:
            logger.exception("Update check cycle failed; will retry next cycle")

        if stop_event.is_set():
            break
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
