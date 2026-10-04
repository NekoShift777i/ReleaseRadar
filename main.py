from providers.github import get_latest_release
from logger import setup_logging
from config import load_config, load_telegram_config
from config_validation import ConfigError
from datetime import datetime, timezone
from update_logic import should_notify, UpdateResult
from notifications import get_pending_notifications
from telegram_notifier import send_update_notification
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from telegram_handlers import handle_version_updated, handle_status
from scheduler import get_check_interval, run_periodic_checks
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



def check_updates(config: dict) -> list[UpdateResult]:
    results: list[UpdateResult] = []

    for software in config["software"]:
        if not software["enabled"]:
            logger.info(
                "%s is disabled",
                software["name"],
            )
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

            include_prerelease = (
                software["channel"] == "prerelease"
            )

            release = get_latest_release(
                    software["repository"],
                    include_prerelease=include_prerelease,
                )

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
                state["current_version"] != release.version
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

        except Exception:
            logger.exception(
                "Failed to check %s",
                software["name"],
            )

    return results




async def send_pending_notifications(
        application: Application,
        chat_id: int,
        pending_notifications: list[UpdateResult],
) -> None:
    for result in pending_notifications:
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

        except Exception:
            logger.exception(
                "Failed to send notification for %s",
                result.software_name
            )


def main() -> None:
    setup_logging()
    logger.info("ReleaseRadar started")

    config = load_config()
    interval = get_check_interval(config)

    telegram_token, telegram_chat_id = load_telegram_config()
    initialize_database()

    async def post_init(application: Application) -> None:
        stop_event = asyncio.Event()

        async def check_once() -> None:
            logger.info("Update check cycle started")
            results = await asyncio.to_thread(check_updates, config)
            if stop_event.is_set():
                return
            await send_pending_notifications(
                application, telegram_chat_id, get_pending_notifications(results),
            )
            logger.info("Update check cycle finished; next check in %s seconds", interval)

        application.bot_data["check_stop_event"] = stop_event
        application.bot_data["check_task"] = asyncio.create_task(
            run_periodic_checks(check_once, stop_event, interval),
            name="release-radar-checks",
        )

    async def post_stop(application: Application) -> None:
        stop_event = application.bot_data.get("check_stop_event")
        task = application.bot_data.get("check_task")
        if stop_event is not None:
            stop_event.set()
        if task is not None:
            # Let an in-flight worker finish before shutting down the bot/database.
            await task

    application = (
        Application.builder()
        .token(telegram_token)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )

    application.bot_data["config"] = config
    application.bot_data["telegram_chat_id"] = telegram_chat_id
    application.add_handler(CommandHandler("status", handle_status))

    application.add_handler(
        CallbackQueryHandler(
            handle_version_updated,
            pattern=r"^version_updated:",
        )
    )

    logger.info("Telegram bot started")

    application.run_polling()

if __name__ == "__main__":
    try:
        main()
    except ConfigError as error:
        logger.error("%s", error)
        raise SystemExit(1)
    except Exception:
        logger.exception("ReleaseRadar crashed")
        raise
