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
from status import get_status_messages
from check_locks import SoftwareCheckLocks
from message_editing import edit_callback_message
from config_validation import parse_notification_button_retention
from datetime import datetime
from zoneinfo import ZoneInfo

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


CHECK_PAGE_SIZE = 8
CONFIRM_REQUEST_TTL = 60 * 60


def build_check_keyboard(config: dict, page: int = 0) -> InlineKeyboardMarkup:
    """Show one page of enabled programs; keep selection indices stable."""
    enabled = [item for item in config["software"] if item["enabled"]]
    page_count = max(1, (len(enabled) + CHECK_PAGE_SIZE - 1) // CHECK_PAGE_SIZE)
    if page < 0 or page >= page_count:
        raise ValueError("Invalid check page")
    start = page * CHECK_PAGE_SIZE
    rows = [
        [InlineKeyboardButton(item["name"], callback_data=f"check_select:{index}")]
        for index, item in enumerate(enabled[start:start + CHECK_PAGE_SIZE], start)
    ]
    if page_count > 1:
        navigation = []
        if page > 0:
            navigation.append(InlineKeyboardButton("◀️ Назад", callback_data=f"check_page:{page - 1}"))
        navigation.append(InlineKeyboardButton(f"{page + 1}/{page_count}", callback_data="check_page_info"))
        if page + 1 < page_count:
            navigation.append(InlineKeyboardButton("Далее ▶️", callback_data=f"check_page:{page + 1}"))
        rows.append(navigation)
    rows.append([InlineKeyboardButton("🔄 Проверить все", callback_data="check_all")])
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data="check_cancel")])
    return InlineKeyboardMarkup(rows)


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
    message = update.effective_message
    if message is None or not is_authorized(update, context):
        return
    if context.bot_data.get("manual_checks") is None:
        await message.reply_text("Бот ещё запускается. Попробуйте чуть позже.", parse_mode=None)
        return
    if not any(item["enabled"] for item in context.bot_data["config"]["software"]):
        await message.reply_text("Нет включённых программ для проверки.", parse_mode=None)
        return
    await message.reply_text(
        "Выберите программу для проверки:",
        reply_markup=build_check_keyboard(context.bot_data["config"]),
        parse_mode=None,
    )


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
    config = context.bot_data["config"]
    enabled = [item for item in config["software"] if item["enabled"]]
    if data == "check_cancel":
        await query.answer("Выбор проверки отменён.")
        await edit_callback_message(
            query, text="Выбор проверки отменён.", reply_markup=None, edit_text=True
        )
        return
    if data == "check_page_info":
        await query.answer()
        return
    if data.startswith("check_page:"):
        match = re.fullmatch(r"check_page:([0-9]+)", data)
        page_count = max(1, (len(enabled) + CHECK_PAGE_SIZE - 1) // CHECK_PAGE_SIZE)
        if match is None or int(match.group(1)) >= page_count:
            await query.answer("Страница устарела. Откройте /check заново.", show_alert=True)
            return
        await query.answer()
        await edit_callback_message(
            query, reply_markup=build_check_keyboard(config, int(match.group(1)))
        )
        return
    if data == "check_all":
        software_id = None
        label = "всех программ"
    else:
        match = re.fullmatch(r"check_select:([0-9]+)", data)
        if match is None or int(match.group(1)) >= len(enabled):
            await query.answer("Кнопка устарела. Откройте /check заново.", show_alert=True)
            return
        item = enabled[int(match.group(1))]
        software_id = item["id"]
        label = item["name"]

    requests = context.bot_data.get("manual_checks")
    if requests is None:
        await query.answer("Бот ещё запускается.", show_alert=True)
        return
    acknowledged = asyncio.Event()

    async def send_result(text: str) -> None:
        await acknowledged.wait()
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=text, parse_mode=None
        )

    decision = requests.request(send_result, software_id=software_id)
    answers = {
        "accepted": f"Запрошена проверка {label}. Сообщу результат после завершения.",
        "busy": "Проверка уже выполняется или запрошена. Вторую не запускаю.",
        "stopping": "Бот останавливается. Новая проверка не запущена.",
    }
    try:
        await query.answer(answers[decision], show_alert=decision != "accepted")
        if decision == "accepted":
            await edit_callback_message(
                query,
                text=f"Запрошена проверка {label}. Ожидайте результат.",
                reply_markup=None,
                edit_text=True,
            )
    except TelegramError:
        logger.warning("Failed to acknowledge selected check", exc_info=True)
    finally:
        acknowledged.set()


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
        await query.answer(
            "Подтверждение недействительно. Откройте /confirm заново.",
            show_alert=True,
        )
        return

    if time.time() - request["created_at"] >= CONFIRM_REQUEST_TTL:
        requests.pop(token, None)

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
        await query.answer(
            "Обнаруженная версия изменилась. Откройте /confirm заново.",
            show_alert=True,
        )
        return

    if state["current_version"] == version:
        requests.pop(token, None)
        await query.answer(
            "Эта версия уже установлена.",
            show_alert=True,
        )
        return

    if not mark_version_updated(software_id, version):
        await query.answer(
            "Не удалось подтвердить установку.",
            show_alert=True,
        )
        return

    requests.pop(token, None)

    await query.answer("Версия отмечена установленной.")

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


async def handle_status(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or not is_authorized(update, context):
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
        elif mark_version_updated(button["software_id"], button["version"]):
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

    await query.answer(answer, show_alert=show_alert)
    await edit_callback_message(query, reply_markup=None)



async def handle_version_skip(
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
    match = (
        re.fullmatch(r"version_skip:v1:([0-9a-f]{32})", data)
        if isinstance(data, str)
        else None
    )

    if match is None:
        await query.answer("Недействительная кнопка.", show_alert=True)
        return

    try:
        retention = parse_notification_button_retention(
            context.bot_data["config"].get(
                "notification_button_retention", "30d"
            )
        )

        button = get_valid_notification_button(
            match.group(1),
            retention,
        )

        if button is None:
            await query.answer(
                "Кнопка устарела. Используйте новое уведомление.",
                show_alert=True,
            )
            return

        software_id = button["software_id"]
        version = button["version"]
        state = get_software_state(software_id)

        if (
            state is None
            or state["latest_version"] != version
            or state["current_version"] == version
            or is_release_skipped(software_id, version)
        ):
            await query.answer(
                "Этот выпуск уже обработан или уведомление устарело.",
                show_alert=True,
            )
            return



        pending = context.user_data.get("pending_version_skip")

        if isinstance(pending, dict):
            if (
                pending.get("token") == match.group(1)
                and pending.get("chat_id") == query.message.chat_id
                and pending.get("message_id") == query.message.message_id
            ):
                await query.answer("Ожидается ввод причины пропуска.")
            else:
                await query.answer(
                    "Сначала завершите или отмените предыдущий пропуск.",
                    show_alert=True,
                )
            return

        request_token = secrets.token_hex(16)

        context.user_data["pending_version_skip"] = {
            "software_id": software_id,
            "version": version,
            "token": match.group(1),
            "chat_id": query.message.chat_id,
            "message_id": query.message.message_id,
            "request_token": request_token,
        }

    except Exception:
        logger.exception("Failed to prepare release skip")
        await query.answer(
            "Не удалось подготовить пропуск версии.",
            show_alert=True,
        )
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ Отмена",
                    callback_data=f"version_skip_cancel:v1:{request_token}",
                )
            ]
        ]
    )

    await query.answer()

    await query.message.reply_text(
        f"Укажите причину пропуска версии {version}.\n\n"
        "Отправьте причину обычным сообщением "
        "или нажмите «Отмена».",
        reply_markup=keyboard,
        parse_mode=None,
    )



async def handle_version_skip_reason(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if message is None or not is_authorized(update, context):
        return

    pending = context.user_data.get("pending_version_skip")
    if pending is None:
        return

    reason = (message.text or "").strip()

    if not reason:
        await message.reply_text(
            "Причина не может быть пустой.",
            parse_mode=None,
        )
        return

    if len(reason) > 1000:
        await message.reply_text(
            "Причина слишком длинная. Максимум 1000 символов.",
            parse_mode=None,
        )
        return

    try:
        retention = parse_notification_button_retention(
            context.bot_data["config"].get(
                "notification_button_retention", "30d"
            )
        )

        button = get_valid_notification_button(
            pending["token"],
            retention,
        )

        state = get_software_state(pending["software_id"])

        if (
            button is None
            or button["software_id"] != pending["software_id"]
            or button["version"] != pending["version"]
            or state is None
            or state["latest_version"] != pending["version"]
            or state["current_version"] == pending["version"]
        ):
            context.user_data.pop("pending_version_skip", None)
            await message.reply_text(
                "Выпуск больше не актуален. Пропуск отменён.",
                parse_mode=None,
            )
            return

        saved = skip_release(
            pending["software_id"],
            pending["version"],
            reason,
        )

    except Exception:
        logger.exception("Failed to save release skip")
        await message.reply_text(
            "Не удалось сохранить пропуск. Попробуйте ещё раз.",
            parse_mode=None,
        )
        return

    context.user_data.pop("pending_version_skip", None)

    if saved:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=pending["chat_id"],
                message_id=pending["message_id"],
                reply_markup=None,
            )
        except TelegramError:
            logger.warning(
                "Failed to remove buttons after skipping %s %s",
                pending["software_id"],
                pending["version"],
                exc_info=True,
            )

    if saved:
        await message.reply_text(
            f"⏭️ Версия {pending['version']} пропущена.\n"
            f"Причина: {reason}",
            parse_mode=None,
        )
    else:
        await message.reply_text(
            "Этот выпуск уже был пропущен.",
            parse_mode=None,
        )



async def handle_version_skip_cancel(
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
        r"version_skip_cancel:v1:([0-9a-f]{32})",
        query.data or "",
    )

    if match is None:
        await query.answer(
            "Кнопка отмены устарела.",
            show_alert=True,
        )
        return

    pending = context.user_data.get("pending_version_skip")

    if (
        not isinstance(pending, dict)
        or pending.get("request_token") != match.group(1)
        ):
        await query.answer(
            "Этот запрос уже недействителен.",
            show_alert=True,
        )
        return

    context.user_data.pop("pending_version_skip", None)

    await query.answer("Пропуск отменён.")

    await edit_callback_message(
        query,
        text="Ввод причины пропуска отменён.",
        reply_markup=None,
        edit_text=True,
    )




def get_pending_release(software: dict, locks: SoftwareCheckLocks):
    """Fetch release and recheck stored state under a shared reservation.

    Return (release, state) or None if busy or no longer pending.
    """
    with locks.reserve(software["id"]) as acquired:
        if not acquired:
            return None
        release = get_latest_release(software)
        state = get_software_state(software["id"])
        if (state is None or state["latest_version"] is None
                or state["current_version"] == state["latest_version"]
                or state["latest_version"] != release.version):
            return None
        if (
            state is None
            or state["latest_version"] is None
            or state["current_version"] == state["latest_version"]
            or state["latest_version"] != release.version
            or is_release_skipped(software["id"], release.version)
        ):
            return None
        return release, state


async def handle_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resend outstanding notifications without confirming or marking them notified."""
    message = update.effective_message
    chat = update.effective_chat
    if message is None or not is_authorized(update, context):
        return

    config = context.bot_data["config"]
    pending = []
    for software in config["software"]:
        if not software["enabled"]:
            continue
        state = await asyncio.to_thread(get_software_state, software["id"])
        if (state is not None and state["latest_version"] is not None
                and state["current_version"] != state["latest_version"]):
            pending.append(software)

    if not pending:
        await message.reply_text("Неподтверждённых обновлений нет.", parse_mode=None)
        return

    locks = context.bot_data["check_locks"]
    sent = failed = skipped = 0
    for software in pending:
        try:
            # Keep network fetch and state validation under the same reservation.
            # No database writes are performed by /pending.
            pending_release = await asyncio.to_thread(get_pending_release, software, locks)
            if pending_release is None:
                skipped += 1
                continue
            release, state = pending_release
            result = UpdateResult(
                software_id=software["id"], software_name=software["name"],
                current_version=state["current_version"],
                latest_version=state["latest_version"], release_url=release.url,
                update_available=True, notify_required=False,
            )
            await send_update_notification(context.bot, chat.id, result)
            sent += 1
        except Exception:
            failed += 1
            logger.exception("Failed to resend notification for %s", software["name"])

    await message.reply_text(
        f"Повторных уведомлений отправлено: {sent}.\n"
        f"Пропущено (занято или версия изменилась): {skipped}.\n"
        f"Ошибок: {failed}.", parse_mode=None,
    )


def format_skipped_at(value: str) -> str:
    """Format a UTC timestamp in Kamchatka local time."""
    try:
        timestamp = datetime.fromisoformat(value)

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(
                tzinfo=ZoneInfo("UTC")
            )

        local_time = timestamp.astimezone(
            ZoneInfo("Asia/Kamchatka")
        )

        return local_time.strftime(
            "%d.%m.%Y %H:%M:%S"
        ) + " (Камчатка)"

    except (ValueError, TypeError):
        return str(value)


async def handle_skipped(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Show the history of skipped releases."""
    message = update.effective_message

    if message is None or not is_authorized(update, context):
        return

    try:
        releases = await asyncio.to_thread(get_skipped_releases)
    except Exception:
        logger.exception("Failed to read skipped releases")
        await message.reply_text(
            "Не удалось получить историю пропущенных выпусков.",
            parse_mode=None,
        )
        return

    if not releases:
        await message.reply_text(
            "История пропущенных выпусков пуста.",
            parse_mode=None,
        )
        return

    names = {
        item["id"]: item["name"]
        for item in context.bot_data["config"]["software"]
    }

    total = len(releases)
    releases = releases[:20]

    for release in releases:
        name = names.get(
            release["software_id"],
            release["software_id"],
        )

        await message.reply_text(
            f"⏭️ {name}\n"
            f"Версия: {release['version']}\n"
            f"Причина: {release['reason']}\n"
            f"Дата пропуска: {format_skipped_at(release['skipped_at'])}",
            parse_mode=None,
        )
    if total > 20:
        await message.reply_text(
            f"Показаны последние 20 из {total} пропущенных выпусков.",
            parse_mode=None,
        )
