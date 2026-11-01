"""Настройка журналирования с сокрытием секретов."""

import logging
import os
import re
import sys


class SecretRedactingFormatter(logging.Formatter):
    """Скрывает секреты в окончательно сформированном сообщении, включая traceback."""

    _telegram_url = re.compile(r"(https?://api\.telegram\.org/bot)[^/\s?]+", re.IGNORECASE)
    _github_token = re.compile(r"\b(?:github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+)\b")
    _auth_header = re.compile(r"(?i)(\b(?:Authorization|PRIVATE-TOKEN)\s*[:=]\s*(?:Bearer\s+|token\s+)?)[^\s,;\]\}\"']+")

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        message = self._telegram_url.sub(r"\1[СКРЫТО]", message)
        message = self._github_token.sub("[СКРЫТО]", message)
        message = self._auth_header.sub(r"\1[СКРЫТО]", message)

        # Помимо стандартных ключей защищаем пользовательские *_TOKEN,
        # *_SECRET, *_PASSWORD, *_API_KEY (например, ключи GitLab).
        for name, value in os.environ.items():
            if not name.upper().endswith(("_TOKEN", "_SECRET", "_PASSWORD", "_API_KEY")):
                continue
            if value and len(value) >= 8:
                message = message.replace(value, "[СКРЫТО]")
        return message


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)-8s | "
            "%(name)s | %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("release-radar.log", encoding="utf-8"),
        ],
        force=True,
    )

    for handler in logging.getLogger().handlers:
        handler.setFormatter(SecretRedactingFormatter(handler.formatter._fmt, datefmt="%Y-%m-%d %H:%M:%S"))

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
