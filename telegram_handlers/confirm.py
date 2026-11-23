"""Manual version confirmation handlers.

Compatibility dependencies are resolved on the package to preserve existing
public entry points and test patch targets.
"""

import logging
import re
import secrets
import time
import sys

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import ContextTypes

_parent = sys.modules[__package__]


def get_confirmable_software(config: dict) -> list[dict]:
    """Find programs with a detected version awaiting confirmation."""
    result = []

    for software in config["software"]:
        if not software["enabled"]:
            continue

        state = _parent.get_software_state(software["id"])
        if state is None:
            continue

        current = state["current_version"]
        latest = state["latest_version"]

        if latest and current != latest:
            result.append(software)

    return result



def build_confirm_keyboard(
    software: list[dict],
    context: ContextTypes.DEFAULT_TYPE,
) -> InlineKeyboardMarkup:
    requests = context.user_data.setdefault(
        "confirm_selection_requests", {}
    )
    requests.clear()

    rows = []

    for item in software:
        token = secrets.token_hex(16)
        requests[token] = item["id"]

        rows.append([
            InlineKeyboardButton(
                item["name"],
                callback_data=f"confirm_select:v1:{token}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            "❌ Отмена",
            callback_data="confirm_cancel",
        )
    ])

    return InlineKeyboardMarkup(rows)



async def handle_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Show programs whose detected versions can be confirmed."""
    message = update.effective_message

    if message is None or not _parent.is_authorized(update, context):
        return

    software = _parent.get_confirmable_software(
        context.bot_data["config"]
    )

    if not software:
        await message.reply_text(
            "Нет программ с неподтверждёнными обновлениями.",
            parse_mode=None,
        )
        return

    await message.reply_text(
        "Выберите программу, обновление которой хотите подтвердить:",
        reply_markup=_parent.build_confirm_keyboard(software, context),
        parse_mode=None,
    )



async def handle_confirm_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None:
        return

    if not _parent.is_authorized(update, context):
        await query.answer("Доступ запрещён.", show_alert=True)
        return

    data = query.data
    if not isinstance(data, str):
        await query.answer("Недействительная кнопка.", show_alert=True)
        return

    
    cancel_match = re.fullmatch(
        r"confirm_cancel:v1:([0-9a-f]{32})",
        data,
    )

    if cancel_match is not None:
        token = cancel_match.group(1)
        requests = context.user_data.get("confirm_requests", {})

        if requests.pop(token, None) is None:
            await query.answer(
                "Подтверждение уже недействительно.",
                show_alert=True,
            )
            return

        await query.answer("Подтверждение отменено.")
        await _parent.edit_callback_message(
            query,
            text="Подтверждение обновления отменено.",
            reply_markup=None,
            edit_text=True,
        )
        return


    if data == "confirm_cancel":
        await query.answer("Выбор программы отменён.")
        await _parent.edit_callback_message(
        query,
            text="Выбор программы для подтверждения отменён.",
            reply_markup=None,
            edit_text=True,
        )
        return


    match = re.fullmatch(
        r"confirm_select:v1:([0-9a-f]{32})",
        data,
    )

    if match is None:
        await query.answer("Недействительная кнопка.", show_alert=True)
        return

    selection_token = match.group(1)
    selection_requests = context.user_data.get(
        "confirm_selection_requests", {}
    )

    software_id = selection_requests.pop(selection_token, None)

    if software_id is None:
        await query.answer(
            "Список устарел. Откройте /confirm заново.",
            show_alert=True,
        )
        return

    item = next(
        (
            software
            for software in context.bot_data["config"]["software"]
            if software["id"] == software_id
            and software["enabled"]
        ),
        None,
    )

    if item is None:
        await query.answer(
            "Программа больше недоступна.",
            show_alert=True,
        )
        return

    state = _parent.get_software_state(software_id)

    if state is None:
        await query.answer(
            "Состояние программы не найдено.",
            show_alert=True,
        )
        return

    if (
        not state["latest_version"]
        or state["current_version"] == state["latest_version"]
    ):
        await query.answer(
            "Для этой программы больше нет неподтверждённого обновления.",
            show_alert=True,
        )
        return


    current = state["current_version"]
    latest = state["latest_version"]


    now = time.time()
    requests = context.user_data.setdefault("confirm_requests", {})

    expired_tokens = [
        key
        for key, request in requests.items()
        if now - request["created_at"] >= _parent.CONFIRM_REQUEST_TTL
    ]

    for key in expired_tokens:
        requests.pop(key, None)

    token = secrets.token_hex(16)

    requests[token] = {
        "software_id": item["id"],
        "version": latest,
        "created_at": now,
    }


    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Подтвердить установку",
                callback_data=f"confirm_apply:v1:{token}",
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Отмена",
                callback_data=f"confirm_cancel:v1:{token}",
            )
        ],
    ])

    await query.answer()
    await _parent.edit_callback_message(
        query,
        text=(
            f"Программа: {item['name']}\n"
            f"Установленная версия: {current}\n"
            f"Обнаруженная версия: {latest}\n\n"
            "Подтвердить установку обнаруженной версии?"
        ),
        reply_markup=keyboard,
        edit_text=True,
    )



async def handle_confirm_apply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None:
        return

    if not _parent.is_authorized(update, context):
        await query.answer("Доступ запрещён.", show_alert=True)
        return

    match = re.fullmatch(
        r"confirm_apply:v1:([0-9a-f]{32})",
        query.data or "",
    )

    if match is None:
        await query.answer(
            "Недействительная кнопка.",
            show_alert=True,
        )
        return

    token = match.group(1)
    requests = context.user_data.get("confirm_requests", {})
    request = requests.get(token)

    if request is None:
        _parent.logger.info(
            "Manual confirmation rejected: reason=request_not_found, actor_id=%s",
            update.effective_user.id
            if update.effective_user is not None
            else None,
        )

        await query.answer(
            "Подтверждение недействительно. Откройте /confirm заново.",
            show_alert=True,
        )
        return

    if time.time() - request["created_at"] >= _parent.CONFIRM_REQUEST_TTL:
        requests.pop(token, None)
        _parent.logger.info(
            "Manual confirmation rejected: "
            "reason=request_expired, software=%s, version=%s, actor_id=%s",
            request["software_id"],
            request["version"],
            update.effective_user.id
            if update.effective_user is not None
            else None,
        )

        await query.answer(
            "Срок подтверждения истёк. Откройте /confirm заново.",
            show_alert=True,
        )
        return


    software_id = request["software_id"]
    version = request["version"]

    item = next(
        (
            software
            for software in context.bot_data["config"]["software"]
            if software["id"] == software_id
            and software["enabled"]
        ),
        None,
    )

    if item is None:
        await query.answer(
            "Программа больше недоступна.",
            show_alert=True,
        )
        return

    state = _parent.get_software_state(software_id)

    if state is None or state["latest_version"] != version:
        requests.pop(token, None)
        _parent.logger.info(
            "Manual confirmation rejected: "
            "reason=version_mismatch, software=%s, version=%s, actor_id=%s",
            software_id,
            version,
            update.effective_user.id
            if update.effective_user is not None
            else None,
        )
        await query.answer(
            "Обнаруженная версия изменилась. Откройте /confirm заново.",
            show_alert=True,
        )
        return

    if state["current_version"] == version:
        requests.pop(token, None)
        _parent.logger.info(
            "Manual confirmation rejected: "
            "reason=already_installed, software=%s, version=%s, actor_id=%s",
            software_id,
            version,
            update.effective_user.id
            if update.effective_user is not None
            else None,
        )
        await query.answer(
            "Эта версия уже установлена.",
            show_alert=True,
        )
        return

    if not _parent.mark_version_updated(
        software_id,
        version,
        source="telegram_confirm",
        actor_id=(
            update.effective_user.id
            if update.effective_user is not None
            else None
        ),
    ):
        _parent.logger.warning(
            "Manual confirmation rejected: "
            "reason=database_update_rejected, "
            "software=%s, version=%s, actor_id=%s",
            software_id,
            version,
            update.effective_user.id
            if update.effective_user is not None
            else None,
        )

        await query.answer(
            "Не удалось подтвердить установку.",
            show_alert=True,
        )
        return

    requests.pop(token, None)

    try:
        await query.answer("Версия отмечена установленной.")
    except TelegramError:
        _parent.logger.warning(
            "Failed to answer manual version confirmation callback",
            exc_info=True,
        )

    await _parent.edit_callback_message(
        query,
        text=(
            "✅ Обновление подтверждено.\n\n"
            f"Программа: {item['name']}\n"
            f"Установленная версия: {version}"
        ),
        reply_markup=None,
        edit_text=True,
    )


