"""Record incoming Telegram commands without logging their arguments."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from .common import is_authorized

logger = logging.getLogger(__name__)


async def log_telegram_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log commands before regular command handlers execute."""
    message = update.effective_message
    if message is None or not message.text:
        return
    command = message.text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
    user = update.effective_user
    chat = update.effective_chat
    authorized = is_authorized(update, context)
    (logger.info if authorized else logger.warning)(
        "Telegram command: %s | user_id=%s | chat_id=%s | authorized=%s",
        command,
        user.id if user is not None else None,
        chat.id if chat is not None else None,
        authorized,
    )
