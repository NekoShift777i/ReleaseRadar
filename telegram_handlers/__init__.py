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
from . import confirm as _confirm
from . import notifications as _notifications

logger = logging.getLogger(__name__)


def is_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Compatibility entry point for authorization checks and test patches."""
    return _is_authorized(update, context)


CHECK_PAGE_SIZE = 8
CONFIRM_REQUEST_TTL = 60 * 60


def build_check_keyboard(config: dict, page: int = 0) -> InlineKeyboardMarkup:
    return _check.build_check_keyboard(config, page)


def get_confirmable_software(config: dict) -> list[dict]:
    return _confirm.get_confirmable_software(config)



def build_confirm_keyboard(
    software: list[dict],
    context: ContextTypes.DEFAULT_TYPE,
) -> InlineKeyboardMarkup:
    return _confirm.build_confirm_keyboard(software, context)



async def handle_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _check.handle_check(update, context)


async def handle_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _confirm.handle_confirm(update, context)


async def handle_confirm_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _confirm.handle_confirm_selection(update, context)


async def handle_check_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _check.handle_check_selection(update, context)


async def handle_confirm_apply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _confirm.handle_confirm_apply(update, context)


async def handle_version_updated(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _notifications.handle_version_updated(update, context)


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
