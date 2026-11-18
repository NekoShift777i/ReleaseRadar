"""Entry point for an authorized Telegram user."""

import logging

import telegram_handlers as handlers
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def handle_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if message is None or not handlers.is_authorized(update, context):
        return

    text = (
        "ReleaseRadar — отслеживание обновлений программ.\n\n"
        "Доступные команды:\n"
        "/status — состояние отслеживаемых программ\n"
        "/check — проверить наличие обновлений\n"
        "/pending — повторить неподтверждённые уведомления\n"
        "/confirm — подтвердить установку обновления\n"
        "/skipped — показать список пропусков версий"
    )
    try:
        await message.reply_text(text, parse_mode=None)
    except TelegramError:
        logger.warning("Failed to send start message", exc_info=True)
