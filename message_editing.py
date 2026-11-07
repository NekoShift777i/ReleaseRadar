"""Safe edits of Telegram callback messages."""

import logging

from telegram.error import BadRequest, TelegramError

logger = logging.getLogger(__name__)


async def edit_callback_message(query, *, text=None, reply_markup=None, edit_text=False):
    """Edit callback message, returning True on success or a harmless no-op.

    Set edit_text=True to replace text and markup together. Otherwise update
    only the keyboard. The caller must acknowledge the callback separately.
    """
    message = query.message
    if message is not None:
        if edit_text:
            if (getattr(message, "text", None) == text
                    and getattr(message, "reply_markup", None) == reply_markup):
                return True
        elif getattr(message, "reply_markup", None) == reply_markup:
            return True

    try:
        if edit_text:
            await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=None)
        else:
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        return True
    except BadRequest as exc:
        reason = str(exc).lower()
        if "message is not modified" in reason:
            return True
        logger.warning("Cannot edit Telegram message: %s", exc)
    except TelegramError as exc:
        logger.warning(
            "Не удалось изменить сообщение Telegram (%s): %s",
            type(exc).__name__,
            exc,
        )
    return False
