import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class ManualCheckRequests:
    """Reserve manual cycles on the same event loop as the periodic runner."""
    def __init__(self, stop_event: asyncio.Event):
        self.stop_event = stop_event
        self.wake = asyncio.Event()
        self.running = True  # The initial cycle is already reserved.
        self.pending = False
        self.completion = None
        self.software_id: str | None = None

    def request(
        self, completion: Callable[[str], Awaitable[None]], software_id: str | None = None
    ) -> str:
        if self.stop_event.is_set():
            return "stopping"
        if self.running or self.pending:
            return "busy"
        self.pending = True
        self.completion = completion
        self.software_id = software_id
        self.wake.set()
        return "accepted"

    def begin_cycle(self):
        self.running = True
        completion = self.completion
        software_id = self.software_id
        self.completion = None
        self.software_id = None
        self.pending = False
        self.wake.clear()
        return completion, software_id


async def wait_for_next_check(stop_event, interval, manual_requests):
    if manual_requests is None:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
        return
    waiters = [asyncio.create_task(stop_event.wait()), asyncio.create_task(manual_requests.wake.wait())]
    try:
        await asyncio.wait(waiters, timeout=interval, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in waiters:
            if not task.done():
                task.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)


def get_check_interval(config: dict) -> int:
    interval = config.get("check_interval_seconds", 3600)
    if isinstance(interval, bool) or not isinstance(interval, int) or interval <= 0:
        raise ValueError("check_interval_seconds must be a positive integer")
    return interval


async def run_periodic_checks(
    check_once: Callable[[str | None], Awaitable[str | None]],
    stop_event: asyncio.Event,
    interval: int,
    manual_requests: ManualCheckRequests | None = None,
) -> None:
    """Run immediately, then wait after each completed cycle. Never overlap."""
    while not stop_event.is_set():
        completion, software_id = manual_requests.begin_cycle() if manual_requests else (None, None)
        try:
            result = await check_once(software_id)
        except Exception:
            logger.exception("Update check cycle failed; will retry next cycle")
            result = "Не удалось завершить проверку. Подробности — в журнале."

        if completion is not None and not stop_event.is_set():
            try:
                await completion(result or "Проверка завершена.")
            except Exception:
                logger.exception("Failed to send manual check result")
        if manual_requests:
            manual_requests.running = False

        if stop_event.is_set():
            break
        await wait_for_next_check(stop_event, interval, manual_requests)
