from datetime import datetime, timezone

from database import get_software_state
from scheduler import get_check_interval


def format_last_check(value: str | None) -> str:
    if not value:
        return "ещё не было успешной проверки"
    try:
        checked = datetime.fromisoformat(value)
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return checked.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M:%S UTC")
    except ValueError:
        return "не удалось прочитать время из базы"


def split_status_text(text: str, limit: int = 4000) -> list[str]:
    """Bound messages conservatively in UTF-16 units, including emoji."""
    messages = []
    start = 0
    size = 0
    for index, char in enumerate(text):
        units = 2 if ord(char) > 0xFFFF else 1
        if size + units > limit:
            messages.append(text[start:index])
            start = index
            size = 0
        size += units
    if start < len(text):
        messages.append(text[start:])
    return messages


def get_status_messages(config: dict) -> list[str]:
    blocks = [
        "📋 ReleaseRadar — состояние программ\n"
        f"Пауза между проверками: {get_check_interval(config)} сек.\n"
        "Данные по последним успешным проверкам; время — UTC."
    ]
    if not config["software"]:
        blocks.append("Список программ пуст.")
    for software in config["software"]:
        state = get_software_state(software["id"])
        current = state["current_version"] if state is not None else software["current_version"]
        latest = state["latest_version"] if state is not None else None
        checked = state["last_checked_at"] if state is not None else None
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
            f"Последняя успешная проверка: {format_last_check(checked)}\n"
            f"{status}"
        )
    return split_status_text("\n\n".join(blocks))
