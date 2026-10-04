import logging
import re

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from database import get_notification_button, mark_version_updated

logger = logging.getLogger(__name__)


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
