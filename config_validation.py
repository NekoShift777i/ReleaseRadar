import re
from typing import Any


class ConfigError(ValueError):
    """Configuration errors suitable for displaying without a traceback."""


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ConfigError("config.yaml: ожидается набор полей YAML, а не список или пустой файл")

    errors = []

    def unknown_fields(mapping, allowed, path):
        for key in mapping:
            if key not in allowed:
                errors.append(f"{path}: неизвестное поле {key!r}")

    unknown_fields(config, {"software", "check_interval_seconds"}, "config.yaml")
    interval = config.get("check_interval_seconds", 3600)
    if type(interval) is not int or interval <= 0:
        errors.append("check_interval_seconds: ожидается целое число секунд больше нуля")

    software_list = config.get("software")
    if not isinstance(software_list, list):
        errors.append("software: ожидается список программ")
    else:
        ids = set()
        required = {"id", "name", "provider", "repository", "channel", "current_version", "enabled"}
        for index, software in enumerate(software_list):
            path = f"software[{index}]"
            if not isinstance(software, dict):
                errors.append(f"{path}: ожидается набор полей программы")
                continue
            unknown_fields(software, required, path)
            for field in sorted(required):
                if field not in software:
                    errors.append(f"{path}.{field}: обязательное поле отсутствует")
            for field in sorted(required - {"enabled"}):
                if field not in software:
                    continue
                value = software[field]
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{path}.{field}: ожидается непустая строка; версии заключайте в кавычки")
                elif value != value.strip():
                    errors.append(f"{path}.{field}: уберите пробелы в начале и конце")
            if "enabled" in software and type(software["enabled"]) is not bool:
                errors.append(f"{path}.enabled: ожидается true или false без кавычек")
            software_id = software.get("id")
            if isinstance(software_id, str) and software_id.strip():
                if software_id in ids:
                    errors.append(f"{path}.id: повторяющийся идентификатор {software_id!r}")
                ids.add(software_id)
            provider = software.get("provider")
            if isinstance(provider, str) and provider != "github":
                errors.append(f"{path}.provider: сейчас поддерживается только github")
            channel = software.get("channel")
            if isinstance(channel, str) and channel not in {"stable", "prerelease"}:
                errors.append(f"{path}.channel: допустимы stable и prerelease")
            repository = software.get("repository")
            if isinstance(repository, str) and (
                not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
                or any(part in {".", ".."} for part in repository.split("/"))
            ):
                errors.append(f"{path}.repository: ожидается owner/repository, например XTLS/Xray-core")

    if errors:
        raise ConfigError("Ошибки в config.yaml:\n" + "\n".join(f"- {error}" for error in errors))
    return config
