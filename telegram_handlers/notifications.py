"""Handlers for notification action buttons.

Dependencies are resolved through the parent package for compatibility with
existing imports and test patches.
"""

import re
import sys
import logging

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from database import create_notification_button
from update_logic import UpdateResult

logger = logging.getLogger("telegram_notifier")
_parent = sys.modules[__package__]


async def handle_version_updated(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None:
        return
    if not _parent.is_authorized(update, context):
        await query.answer("Доступ запрещён.", show_alert=True)
        return
    if not isinstance(query.data, str):
        await query.answer("Недействительная кнопка.", show_alert=True)
        return
    if not query.data.startswith("version_updated:"):
        await query.answer()
        return

    match = re.fullmatch(r"version_updated:v1:([0-9a-f]{32})", query.data)
    try:
        retention = _parent.parse_notification_button_retention(
            context.bot_data["config"].get(
                "notification_button_retention", "30d"
            )
        )

        button = (
            _parent.get_valid_notification_button(match.group(1), retention)
            if match
            else None
        )
        if button is None:
            # Legacy buttons have no version and cannot be confirmed safely.
            answer = "Эта кнопка устарела. Используйте новое уведомление."
            show_alert = True
        elif _parent.mark_version_updated(
            button["software_id"],
            button["version"],
            source="telegram_notification",
            actor_id=(
                update.effective_user.id
                if update.effective_user is not None
                else None
            ),
        ):
            _parent.logger.info(
                "%s marked as updated: %s", button["software_id"], button["version"]
            )
            pending = context.user_data.get("pending_version_skip")

            if (
                pending is not None
                and pending["software_id"] == button["software_id"]
                and pending["version"] == button["version"]
            ):
                context.user_data.pop("pending_version_skip", None)
            answer = "Версия отмечена как обновлённая"
            show_alert = False
        else:
            answer = "Версия уже отмечена или уведомление устарело. База не изменена."
            show_alert = True
    except Exception:
        _parent.logger.exception("Failed to confirm release")
        await query.answer("Не удалось обновить базу. Попробуйте ещё раз.", show_alert=True)
        return

    try:
        await query.answer(answer, show_alert=show_alert)
    except TelegramError:
        _parent.logger.warning(
            "Failed to answer version confirmation callback",
            exc_info=True,
        )

    await _parent.edit_callback_message(query, reply_markup=None)


async def send_update_notification(
        bot: Bot,
        chat_id: int,
        result: UpdateResult,
) -> None:
    token = create_notification_button(result.software_id, result.latest_version)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Версия обновлена",
                    callback_data=f"version_updated:v1:{token}",
                )
            ],
            [
                InlineKeyboardButton(
                    "⏭️ Пропустить версию",
                    callback_data=f"version_skip:v1:{token}",
                )
            ],
        ]
    )


    message = (
        f"🔔 Доступно обновление {result.software_name}\n\n"
        f"Текущая версия: {result.current_version}\n"
        f"Новая версия: {result.latest_version}\n\n"
        f"{result.release_url}"
    )

    await bot.send_message(
        chat_id=chat_id,
        text=message,
        reply_markup=keyboard,
    )

    logger.info(
        "Update notification sent for %s: %s",
        result.software_name,
        result.latest_version,
    )
