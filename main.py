from providers import get_latest_release
from logger import setup_logging
from config import load_config, load_telegram_config
from config_validation import ConfigError
from datetime import datetime, timezone
from update_logic import should_notify, is_newer_version, UpdateResult
from notifications import get_pending_notifications
from telegram_notifier import send_update_notification
from telegram import BotCommand
from telegram.error import NetworkError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from telegram_handlers import handle_version_updated, handle_status, handle_check, handle_pending
from scheduler import get_check_interval, run_periodic_checks, ManualCheckRequests
from shutdown import ShutdownController, handle_console_interrupt, keep_signal_loop_responsive
from providers.base import CheckCancelled
from threading import Event
from check_locks import SoftwareCheckLocks
from database import (
    initialize_database, 
    get_or_create_software_state,
    update_software_check,
    mark_version_notified,
    get_software_state,
)

import asyncio
import logging

logger = logging.getLogger("main")



def check_updates(
    config: dict,
    stop_event: Event | None = None,
    check_locks: SoftwareCheckLocks | None = None,
    skipped_busy: set[str] | None = None,
) -> list[UpdateResult]:
    results: list[UpdateResult] = []
    if check_locks is None:
        check_locks = SoftwareCheckLocks()

    for software in config["software"]:
        if stop_event is not None and stop_event.is_set():
            break
        if not software["enabled"]:
            logger.info(
                "%s is disabled",
                software["name"],
            )
            continue

        with check_locks.reserve(software["id"]) as acquired:
            if not acquired:
                logger.info("Skipping %s: check already running", software["name"])
                if skipped_busy is not None:
                    skipped_busy.add(software["id"])
                continue
            try:
                state = get_or_create_software_state(
                        software["id"],
                        software["current_version"],
                    )

                logger.info(
                    "%s Current version: %s",
                    software["name"],
                    state["current_version"]
                )

                release = get_latest_release(software, stop_event=stop_event)
                if stop_event is not None and stop_event.is_set():
                    break

                logger.info(
                    "%s latest version: %s",
                    software["name"],
                    release.version,
                )

                # A button may have been pressed while the GitHub request was running.
                state = get_software_state(software["id"])
                if state is None:
                    continue

                update_available = (
                    is_newer_version(state["current_version"], release.version)
                )

                if update_available:
                    logger.info(
                        "%s update available: %s -> %s",
                        software["name"],
                        state["current_version"],
                        release.version,
                    )
                else:
                    logger.info(
                        "%s is up to date",
                        software["name"],
                    )

                update_software_check(
                    software["id"],
                    release.version,
                    datetime.now(timezone.utc).isoformat(),
                )

                notify_required = should_notify(
                    state["current_version"],
                    release.version,
                    state["last_notified_version"],
                )

                if notify_required:
                    logger.info(
                        "Notification required for %s: %s",
                        software["name"],
                        release.version,
                    )

                result = UpdateResult(
                    software_id=software["id"],
                    software_name=software["name"],
                    current_version=state["current_version"],
                    latest_version=release.version,
                    release_url=release.url,
                    update_available=update_available,
                    notify_required=notify_required,
                )

                results.append(result)

            except CheckCancelled:
                logger.info("Release check stopped")
                break
            except Exception:
                if stop_event is not None and stop_event.is_set():
                    break
                logger.exception(
                    "Failed to check %s",
                    software["name"],
                )

    return results




async def send_pending_notifications(
        application: Application,
        chat_id: int,
        pending_notifications: list[UpdateResult],
        stop_event: Event | None = None,
) -> tuple[int, int]:
    sent = failed = 0
    for result in pending_notifications:
        if stop_event is not None and stop_event.is_set():
            break
        try:
            state = get_software_state(result.software_id)
            if state is None or not should_notify(
                state["current_version"], result.latest_version,
                state["last_notified_version"],
            ):
                continue
            result.current_version = state["current_version"]
            await send_update_notification(
                application.bot,
                chat_id,
                result,
            )

            mark_version_notified(
                result.software_id,
                result.latest_version,
            )
            sent += 1

        except Exception:
            failed += 1
            logger.exception(
                "Failed to send notification for %s",
                result.software_name
            )
    return sent, failed



async def handle_telegram_error(update, context) -> None:
    error = context.error

    if isinstance(error, NetworkError):
        logger.warning(
            "Временная сетевая ошибка Telegram: %s: %s",
            type(error).__name__,
            error,
        )
        return

    logger.error(
        "Неожиданная ошибка Telegram",
        exc_info=(
            type(error),
            error,
            error.__traceback__,
        ) if error is not None else None,
    )


def main() -> None:
    setup_logging()
    logger.info("ReleaseRadar started")

    config = load_config()
    interval = get_check_interval(config)

    telegram_token, telegram_chat_id = load_telegram_config()
    initialize_database()
    shutdown = ShutdownController()
    check_locks = SoftwareCheckLocks()

    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("status", "Состояние отслеживаемых программ"),
            BotCommand("check", "Проверить наличие обновлений"),
            BotCommand("pending", "Повторить неподтверждённые уведомления"),
        ])
        stop_event = asyncio.Event()
        shutdown.bind(stop_event)
        if shutdown.worker_stop.is_set():
            stop_event.set()

        async def check_once() -> str | None:
            logger.info("Update check cycle started")
            skipped_busy: set[str] = set()
            results = await asyncio.to_thread(
                check_updates, config, shutdown.worker_stop, check_locks, skipped_busy
            )
            if shutdown.worker_stop.is_set():
                return
            sent, failed = await send_pending_notifications(
                application, telegram_chat_id, get_pending_notifications(results),
                shutdown.worker_stop,
            )
            logger.info("Update check cycle finished; next check in %s seconds", interval)
            enabled_count = sum(software["enabled"] for software in config["software"])
            check_errors = enabled_count - len(results) - len(skipped_busy)
            return (
                "Проверка завершена.\n"
                f"Успешно проверено: {len(results)} из {enabled_count}.\n"
                f"Ошибок проверки: {check_errors}.\n"
                f"Пропущено из-за занятости: {len(skipped_busy)}.\n"
                f"Новых уведомлений отправлено: {sent}.\n"
                f"Ошибок отправки: {failed}.\n"
                "Состояние программ: /status"
            )

        application.bot_data["check_stop_event"] = stop_event
        manual_requests = ManualCheckRequests(stop_event)
        application.bot_data["manual_checks"] = manual_requests
        application.bot_data["signal_task"] = asyncio.create_task(keep_signal_loop_responsive(stop_event))
        application.bot_data["check_task"] = asyncio.create_task(
            run_periodic_checks(check_once, stop_event, interval, manual_requests),
            name="release-radar-checks",
        )

    async def post_stop(application: Application) -> None:
        logger.info("Stopping ReleaseRadar; waiting for any active request to finish")
        shutdown.request_stop()
        stop_event = application.bot_data.get("check_stop_event")
        task = application.bot_data.get("check_task")
        if stop_event is not None:
            stop_event.set()
        if task is not None:
            # Let an in-flight worker finish before shutting down the bot/database.
            await task
        signal_task = application.bot_data.get("signal_task")
        if signal_task is not None:
            await signal_task

    application = (
        Application.builder()
        .token(telegram_token)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )

    application.bot_data["check_locks"] = check_locks
    application.bot_data["config"] = config
    application.bot_data["telegram_chat_id"] = telegram_chat_id
    application.add_error_handler(handle_telegram_error)
    application.add_handler(CommandHandler("status", handle_status))
    application.add_handler(CommandHandler("check", handle_check))
    application.add_handler(CommandHandler("pending", handle_pending))

    application.add_handler(
        CallbackQueryHandler(
            handle_version_updated,
            pattern=r"^version_updated:",
        )
    )

    logger.info("Telegram bot started")

    with handle_console_interrupt(application, shutdown):
        application.run_polling(stop_signals=None)
    logger.info("ReleaseRadar stopped")

if __name__ == "__main__":
    try:
        main()
    except ConfigError as error:
        logger.error("%s", error)
        raise SystemExit(1)
    except Exception:
        logger.exception("ReleaseRadar crashed")
        raise
