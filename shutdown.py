import asyncio
import logging
import signal
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ShutdownController:
    def __init__(self):
        self.worker_stop = threading.Event()
        self.loop = None
        self.async_stop = None

    def bind(self, event: asyncio.Event) -> None:
        self.loop = asyncio.get_running_loop()
        self.async_stop = event

    def request_stop(self) -> bool:
        first_request = not self.worker_stop.is_set()
        self.worker_stop.set()
        if self.loop is not None and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.async_stop.set)
        return first_request


async def keep_signal_loop_responsive(stop_event: asyncio.Event) -> None:
    # Windows cannot use asyncio.add_signal_handler. Short timer wakes allow
    # Python to dispatch Ctrl+C even while network I/O is idle.
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=0.25)
        except asyncio.TimeoutError:
            pass


@contextmanager
def handle_console_interrupt(application, controller: ShutdownController):
    signals = (signal.SIGINT, signal.SIGTERM)
    previous_handlers = {
        sig: signal.getsignal(sig) for sig in signals
    }

    def interrupt(signum, frame):
        if not controller.request_stop():
            return

        if controller.loop is not None and application.running:
            def stop_application():
                logger.info(
                    "Shutdown requested (%s); stopping new update checks",
                    signal.Signals(signum).name,
                )
                application.stop_running()

            controller.loop.call_soon_threadsafe(stop_application)
        else:
            # Allow run_polling to clean up during initialization.
            raise KeyboardInterrupt

    try:
        for sig in signals:
            signal.signal(sig, interrupt)

        yield

    finally:
        for sig, previous in previous_handlers.items():
            signal.signal(sig, previous)