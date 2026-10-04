from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from config_validation import ConfigError, validate_config

import yaml
import os


CONFIG_PATH = Path("config.yaml")

load_dotenv()



def load_config() -> dict[str, Any]:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = f", строка {mark.line + 1}, столбец {mark.column + 1}" if mark else ""
        raise ConfigError(f"config.yaml{location}: ошибка синтаксиса YAML; проверьте отступы и двоеточия") from error
    except (OSError, UnicodeError) as error:
        raise ConfigError(f"Не удалось прочитать {CONFIG_PATH}: {error}") from error
    return validate_config(config)



def load_telegram_config() -> tuple[str, int]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured")

    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is not configured")

    return token, int(chat_id)
