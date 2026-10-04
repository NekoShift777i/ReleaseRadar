import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from update_logic import UpdateResult
from database import create_notification_button



logger = logging.getLogger(__name__)



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
            ]
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
