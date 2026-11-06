from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from database import get_software_state
from scheduler import get_check_interval


def format_last_check(value: str | None, timezone_name: str = "UTC") -> str:
    if not value:
        return "ещё не было успешной проверки"
    try:
        checked = datetime.fromisoformat(value)
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return checked.astimezone(ZoneInfo(timezone_name)).strftime("%d.%m.%Y %H:%M:%S") + f" ({timezone_name})"
    except ValueError:
        return "не удалось прочитать время из базы"


def _telegram_units(text: str) -> int:
    """Measure Telegram message length in UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def split_status_blocks(blocks: list[str], limit: int = 4000) -> list[str]:
    """Pack complete software blocks into messages without splitting them."""
    if limit <= 0:
        raise ValueError("Message length limit must be positive")

    messages: list[str] = []
    current = ""
    for block in blocks:
        if _telegram_units(block) > limit:
            raise ValueError("A status block exceeds the Telegram message limit")
        candidate = f"{current}\n\n{block}" if current else block
        if _telegram_units(candidate) <= limit:
            current = candidate
        else:
            messages.append(current)
            current = block
    if current:
        messages.append(current)
    return messages


def get_status_messages(config: dict) -> list[str]:
    timezone_name = config.get("timezone", "UTC")
    blocks = [
        "📋 ReleaseRadar — состояние программ\n"
        f"Пауза между проверками: {get_check_interval(config)} сек.\n"
        f"Данные по последним успешным проверкам; время — {timezone_name}."
    ]
    if not config["software"]:
        blocks.append("Список программ пуст.")
    for software in config["software"]:
        state = get_software_state(software["id"])
        current = state["current_version"] if state is not None else software["current_version"]
        latest = state["latest_version"] if state is not None else None
        checked = state["last_checked_at"] if state is not None else None
        last_error = state["last_error"] if state is not None and "last_error" in state.keys() else None
        last_error_at = state["last_error_at"] if state is not None and "last_error_at" in state.keys() else None
        if not software["enabled"]:
            status = "⏸ Проверка отключена"
        elif latest is None:
            status = "⏳ Нет данных о последнем релизе"
        elif current == latest:
            status = "✅ Установлена последняя обнаруженная версия"
        else:
            status = "🔔 Обнаружена другая версия; обновление не подтверждено"
        source = " (из конфигурации)" if state is None else ""
        blocks.append(
            f"{software['name']} ({software['id']})\n"
            f"Канал: {software['channel']}\n"
            f"Установленная версия: {current}{source}\n"
            f"Последний обнаруженный релиз: {latest or 'ещё неизвестен'}\n"
            f"Последняя успешная проверка: {format_last_check(checked, timezone_name)}\n"
            f"{status}"
            + (f"\n⚠️ Последняя ошибка: {last_error}"
               f"\nВремя ошибки: {format_last_check(last_error_at, timezone_name)}"
               if last_error else "")
        )
    return split_status_blocks(blocks)
