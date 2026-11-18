import logging
import asyncio
import re
import secrets
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from database import (
    get_valid_notification_button,
    mark_version_updated,
    get_software_state,
    is_release_skipped,
    skip_release,
    get_skipped_releases,
)
from providers import get_latest_release
from telegram_notifier import send_update_notification
from update_logic import UpdateResult
from check_locks import SoftwareCheckLocks
from message_editing import edit_callback_message
from config_validation import parse_notification_button_retention
from datetime import datetime
from zoneinfo import ZoneInfo

from .common import is_authorized as _is_authorized
from .status import handle_status
from . import check as _check
from . import skipped as _skipped

logger = logging.getLogger(__name__)


def is_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Compatibility entry point for authorization checks and test patches."""
    return _is_authorized(update, context)


CHECK_PAGE_SIZE = 8
CONFIRM_REQUEST_TTL = 60 * 60


def build_check_keyboard(config: dict, page: int = 0) -> InlineKeyboardMarkup:
    return _check.build_check_keyboard(config, page)


def get_confirmable_software(config: dict) -> list[dict]:
    """Find programs with a detected version awaiting confirmation."""
    result = []

    for software in config["software"]:
        if not software["enabled"]:
            continue

        state = get_software_state(software["id"])
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



async def handle_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _check.handle_check(update, context)


async def handle_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Show programs whose detected versions can be confirmed."""
    message = update.effective_message

    if message is None or not is_authorized(update, context):
        return

    software = get_confirmable_software(
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
        reply_markup=build_confirm_keyboard(software, context),
        parse_mode=None,
    )


async def handle_confirm_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None:
        return

    if not is_authorized(update, context):
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
        await edit_callback_message(
            query,
            text="Подтверждение обновления отменено.",
            reply_markup=None,
            edit_text=True,
        )
        return


    if data == "confirm_cancel":
        await query.answer("Выбор программы отменён.")
        await edit_callback_message(
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

    state = get_software_state(software_id)

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
        if now - request["created_at"] >= CONFIRM_REQUEST_TTL
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
    await edit_callback_message(
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


async def handle_check_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _check.handle_check_selection(update, context)


async def handle_confirm_apply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None:
        return

    if not is_authorized(update, context):
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
        logger.info(
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

    if time.time() - request["created_at"] >= CONFIRM_REQUEST_TTL:
        requests.pop(token, None)
        logger.info(
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

    state = get_software_state(software_id)

    if state is None or state["latest_version"] != version:
        requests.pop(token, None)
        logger.info(
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
        logger.info(
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

    if not mark_version_updated(
        software_id,
        version,
        source="telegram_confirm",
        actor_id=(
            update.effective_user.id
            if update.effective_user is not None
            else None
        ),
    ):
        logger.warning(
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
        logger.warning(
            "Failed to answer manual version confirmation callback",
            exc_info=True,
        )

    await edit_callback_message(
        query,
        text=(
            "✅ Обновление подтверждено.\n\n"
            f"Программа: {item['name']}\n"
            f"Установленная версия: {version}"
        ),
        reply_markup=None,
        edit_text=True,
    )


async def handle_version_updated(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None:
        return
    if not is_authorized(update, context):
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
        retention = parse_notification_button_retention(
            context.bot_data["config"].get(
                "notification_button_retention", "30d"
            )
        )

        button = (
            get_valid_notification_button(match.group(1), retention)
            if match
            else None
        )
        if button is None:
            # Legacy buttons have no version and cannot be confirmed safely.
            answer = "Эта кнопка устарела. Используйте новое уведомление."
            show_alert = True
        elif mark_version_updated(
            button["software_id"],
            button["version"],
            source="telegram_notification",
            actor_id=(
                update.effective_user.id
                if update.effective_user is not None
                else None
            ),
        ):
            logger.info(
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
        logger.exception("Failed to confirm release")
        await query.answer("Не удалось обновить базу. Попробуйте ещё раз.", show_alert=True)
        return

    try:
        await query.answer(answer, show_alert=show_alert)
    except TelegramError:
        logger.warning(
            "Failed to answer version confirmation callback",
            exc_info=True,
        )

    await edit_callback_message(query, reply_markup=None)



async def handle_version_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _skipped.handle_version_skip(update, context)



async def handle_version_skip_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _skipped.handle_version_skip_reason(update, context)



async def handle_version_skip_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _skipped.handle_version_skip_cancel(update, context)




def get_pending_release(software: dict, locks: SoftwareCheckLocks):
    return _check.get_pending_release(software, locks)


async def handle_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _check.handle_pending(update, context)


def format_skipped_at(value: str) -> str:
    return _skipped.format_skipped_at(value)


async def handle_skipped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _skipped.handle_skipped(update, context)
