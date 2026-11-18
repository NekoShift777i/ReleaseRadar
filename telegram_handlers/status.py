import asyncio
import logging

import telegram_handlers as handlers
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from status import get_status_messages

logger = logging.getLogger(__name__)


async def handle_status(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if message is None or not handlers.is_authorized(update, context):
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
