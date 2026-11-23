"""Telegram handlers for skipping releases and displaying skip history."""

import asyncio
import importlib
import re
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import ContextTypes

handlers = importlib.import_module(__package__)

async def handle_version_skip(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None:
        return

    if not handlers.is_authorized(update, context):
        await query.answer("Доступ запрещён.", show_alert=True)
        return

    data = query.data
    match = (
        re.fullmatch(r"version_skip:v1:([0-9a-f]{32})", data)
        if isinstance(data, str)
        else None
    )

    if match is None:
        await query.answer("Недействительная кнопка.", show_alert=True)
        return

    try:
        retention = handlers.parse_notification_button_retention(
            context.bot_data["config"].get(
                "notification_button_retention", "30d"
            )
        )

        button = handlers.get_valid_notification_button(
            match.group(1),
            retention,
        )

        if button is None:
            await query.answer(
                "Кнопка устарела. Используйте новое уведомление.",
                show_alert=True,
            )
            return

        software_id = button["software_id"]
        version = button["version"]
        state = handlers.get_software_state(software_id)

        if (
            state is None
            or state["latest_version"] != version
            or state["current_version"] == version
            or handlers.is_release_skipped(software_id, version)
        ):
            await query.answer(
                "Этот выпуск уже обработан или уведомление устарело.",
                show_alert=True,
            )
            return



        pending = context.user_data.get("pending_version_skip")

        if isinstance(pending, dict):
            if (
                pending.get("token") == match.group(1)
                and pending.get("chat_id") == query.message.chat_id
                and pending.get("message_id") == query.message.message_id
            ):
                await query.answer("Ожидается ввод причины пропуска.")
            else:
                await query.answer(
                    "Сначала завершите или отмените предыдущий пропуск.",
                    show_alert=True,
                )
            return

        request_token = secrets.token_hex(16)

        context.user_data["pending_version_skip"] = {
            "software_id": software_id,
            "version": version,
            "token": match.group(1),
            "chat_id": query.message.chat_id,
            "message_id": query.message.message_id,
            "request_token": request_token,
        }

    except Exception:
        handlers.logger.exception("Failed to prepare release skip")
        await query.answer(
            "Не удалось подготовить пропуск версии.",
            show_alert=True,
        )
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ Отмена",
                    callback_data=f"version_skip_cancel:v1:{request_token}",
                )
            ]
        ]
    )

    await query.answer()

    await query.message.reply_text(
        f"Укажите причину пропуска версии {version}.\n\n"
        "Отправьте причину обычным сообщением "
        "или нажмите «Отмена».",
        reply_markup=keyboard,
        parse_mode=None,
    )



async def handle_version_skip_reason(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if message is None or not handlers.is_authorized(update, context):
        return

    pending = context.user_data.get("pending_version_skip")
    if pending is None:
        return

    reason = (message.text or "").strip()

    if not reason:
        await message.reply_text(
            "Причина не может быть пустой.",
            parse_mode=None,
        )
        return

    if len(reason) > 1000:
        await message.reply_text(
            "Причина слишком длинная. Максимум 1000 символов.",
            parse_mode=None,
        )
        return

    try:
        retention = handlers.parse_notification_button_retention(
            context.bot_data["config"].get(
                "notification_button_retention", "30d"
            )
        )

        button = handlers.get_valid_notification_button(
            pending["token"],
            retention,
        )

        state = handlers.get_software_state(pending["software_id"])

        if (
            button is None
            or button["software_id"] != pending["software_id"]
            or button["version"] != pending["version"]
            or state is None
            or state["latest_version"] != pending["version"]
            or state["current_version"] == pending["version"]
        ):
            context.user_data.pop("pending_version_skip", None)
            await message.reply_text(
                "Выпуск больше не актуален. Пропуск отменён.",
                parse_mode=None,
            )
            return

        saved = handlers.skip_release(
            pending["software_id"],
            pending["version"],
            reason,
        )

    except Exception:
        handlers.logger.exception("Failed to save release skip")
        await message.reply_text(
            "Не удалось сохранить пропуск. Попробуйте ещё раз.",
            parse_mode=None,
        )
        return

    context.user_data.pop("pending_version_skip", None)

    if saved:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=pending["chat_id"],
                message_id=pending["message_id"],
                reply_markup=None,
            )
        except TelegramError:
            handlers.logger.warning(
                "Failed to remove buttons after skipping %s %s",
                pending["software_id"],
                pending["version"],
                exc_info=True,
            )

    if saved:
        await message.reply_text(
            f"⏭️ Версия {pending['version']} пропущена.\n"
            f"Причина: {reason}",
            parse_mode=None,
        )
    else:
        await message.reply_text(
            "Этот выпуск уже был пропущен.",
            parse_mode=None,
        )



async def handle_version_skip_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None:
        return

    if not handlers.is_authorized(update, context):
        await query.answer("Доступ запрещён.", show_alert=True)
        return


    match = re.fullmatch(
        r"version_skip_cancel:v1:([0-9a-f]{32})",
        query.data or "",
    )

    if match is None:
        await query.answer(
            "Кнопка отмены устарела.",
            show_alert=True,
        )
        return

    pending = context.user_data.get("pending_version_skip")

    if (
        not isinstance(pending, dict)
        or pending.get("request_token") != match.group(1)
        ):
        await query.answer(
            "Этот запрос уже недействителен.",
            show_alert=True,
        )
        return

    context.user_data.pop("pending_version_skip", None)

    await query.answer("Пропуск отменён.")

    await handlers.edit_callback_message(
        query,
        text="Ввод причины пропуска отменён.",
        reply_markup=None,
        edit_text=True,
    )



def format_skipped_at(value: str) -> str:
    """Format a UTC timestamp in Kamchatka local time."""
    try:
        timestamp = datetime.fromisoformat(value)

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(
                tzinfo=ZoneInfo("UTC")
            )

        local_time = timestamp.astimezone(
            ZoneInfo("Asia/Kamchatka")
        )

        return local_time.strftime(
            "%d.%m.%Y %H:%M:%S"
        ) + " (Камчатка)"

    except (ValueError, TypeError):
        return str(value)



async def handle_skipped(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Show the history of skipped releases."""
    message = update.effective_message

    if message is None or not handlers.is_authorized(update, context):
        return

    try:
        releases = await asyncio.to_thread(handlers.get_skipped_releases)
    except Exception:
        handlers.logger.exception("Failed to read skipped releases")
        await message.reply_text(
            "Не удалось получить историю пропущенных выпусков.",
            parse_mode=None,
        )
        return

    if not releases:
        await message.reply_text(
            "История пропущенных выпусков пуста.",
            parse_mode=None,
        )
        return

    names = {
        item["id"]: item["name"]
        for item in context.bot_data["config"]["software"]
    }

    total = len(releases)
    releases = releases[:20]

    for release in releases:
        name = names.get(
            release["software_id"],
            release["software_id"],
        )

        await message.reply_text(
            f"⏭️ {name}\n"
            f"Версия: {release['version']}\n"
            f"Причина: {release['reason']}\n"
            f"Дата пропуска: {handlers.format_skipped_at(release['skipped_at'])}",
            parse_mode=None,
        )
    if total > 20:
        await message.reply_text(
            f"Показаны последние 20 из {total} пропущенных выпусков.",
            parse_mode=None,
        )
