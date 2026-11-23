from telegram import Update
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)


def is_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Allow only the configured owner in a private chat."""
    user = update.effective_user
    chat = update.effective_chat
    allowed_id = context.bot_data.get("telegram_chat_id")
    return (
        user is not None
        and chat is not None
        and chat.type == "private"
        and allowed_id is not None
        and user.id == allowed_id
        and chat.id == allowed_id
    )
