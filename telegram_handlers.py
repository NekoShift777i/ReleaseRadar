import logging
import asyncio
import re

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from database import get_notification_button, mark_version_updated
from status import get_status_messages

logger = logging.getLogger(__name__)


async def handle_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None or chat.id != context.bot_data.get("telegram_chat_id"):
        return
    requests = context.bot_data.get("manual_checks")
    if requests is None:
        await message.reply_text("Бот ещё запускается. Попробуйте чуть позже.", parse_mode=None)
        return
    if not any(software["enabled"] for software in context.bot_data["config"]["software"]):
        await message.reply_text("Нет включённых программ для проверки.", parse_mode=None)
        return

    acknowledged = asyncio.Event()

    async def send_result(text: str) -> None:
        await acknowledged.wait()
        await message.reply_text(text, parse_mode=None)

    decision = requests.request(send_result)
    answer = {
        "accepted": "Проверка запрошена. Сообщу результат после завершения.",
        "busy": "Проверка уже выполняется или запрошена. Вторую не запускаю.",
        "stopping": "Бот останавливается. Новая проверка не запущена.",
    }[decision]
    try:
        await message.reply_text(answer, parse_mode=None)
    except TelegramError:
        logger.warning("Failed to acknowledge manual check", exc_info=True)
    finally:
        acknowledged.set()


async def handle_status(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return
    # Keep the report in the same chat configured for notifications.
    if chat.id != context.bot_data.get("telegram_chat_id"):
        return
    try:
        messages = await asyncio.to_thread(get_status_messages, context.bot_data["config"])
    except Exception:
        logger.exception("Failed to read status")
        messages = ["Не удалось получить состояние программ. Попробуйте ещё раз."]
    try:
        for text in messages:
            await message.reply_text(text, parse_mode=None)
    except TelegramError:
        logger.warning("Failed to send status", exc_info=True)


async def handle_version_updated(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None or not isinstance(query.data, str):
        return
    if not query.data.startswith("version_updated:"):
        await query.answer()
        return

    match = re.fullmatch(r"version_updated:v1:([0-9a-f]{32})", query.data)
    try:
        button = get_notification_button(match.group(1)) if match else None
        if button is None:
            # Legacy buttons have no version and cannot be confirmed safely.
            answer = "Эта кнопка устарела. Используйте новое уведомление."
            show_alert = True
        elif mark_version_updated(button["software_id"], button["version"]):
            logger.info(
                "%s marked as updated: %s", button["software_id"], button["version"]
            )
            answer = "Версия отмечена как обновлённая"
            show_alert = False
        else:
            answer = "Версия уже отмечена или уведомление устарело. База не изменена."
            show_alert = True
    except Exception:
        logger.exception("Failed to confirm release")
        await query.answer("Не удалось обновить базу. Попробуйте ещё раз.", show_alert=True)
        return

    await query.answer(answer, show_alert=show_alert)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        logger.warning("Cannot remove notification button", exc_info=True)
