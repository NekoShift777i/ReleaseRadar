import re
from typing import Any
from urllib.parse import urlsplit


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
        gitlab_optional = {"gitlab_url", "token_env", "prerelease_pattern"}
        github_optional = {"release_filter"}
        for index, software in enumerate(software_list):
            path = f"software[{index}]"
            if isinstance(software, dict):
                name = software.get("name")
                identifier = software.get("id")
                details = []
                if isinstance(name, str) and name.strip():
                    details.append(f"название: {name.strip()!r}")
                if isinstance(identifier, str) and identifier.strip():
                    details.append(f"id: {identifier.strip()!r}")
                if details:
                    path += " (" + ", ".join(details) + ")"
            if not isinstance(software, dict):
                errors.append(f"{path}: ожидается набор полей программы")
                continue
            unknown_fields(software, required | gitlab_optional | github_optional, path)
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
            if isinstance(provider, str) and provider not in {"github", "gitlab"}:
                errors.append(f"{path}.provider: допустимы github и gitlab")
            if "release_filter" in software:
                if provider != "github":
                    errors.append(
                        f"{path}.release_filter: поле доступно только для github"
                    )
                release_filter = software["release_filter"]
                if not isinstance(release_filter, str) or release_filter not in {
                    "strict", "github", "version"
                }:
                    errors.append(
                        f"{path}.release_filter: допустимы strict, github и version"
                    )
            for field in sorted(gitlab_optional & software.keys()):
                if provider != "gitlab":
                    errors.append(f"{path}.{field}: поле доступно только для gitlab")
                value = software[field]
                if not isinstance(value, str) or not value.strip() or value != value.strip():
                    errors.append(f"{path}.{field}: ожидается непустая строка без внешних пробелов")
                    continue
                if field == "gitlab_url":
                    try:
                        parsed = urlsplit(value)
                        port = parsed.port
                        valid = (
                            parsed.scheme == "https" and parsed.hostname
                            and not parsed.username and not parsed.password
                            and not parsed.query and not parsed.fragment
                            and parsed.path in {"", "/"}
                            and not any(char.isspace() for char in value)
                        )
                    except ValueError:
                        valid = False
                    if not valid:
                        errors.append(f"{path}.gitlab_url: ожидается HTTPS-адрес сервера без пути, например https://gitlab.example.com")
                elif field == "token_env" and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
                    errors.append(f"{path}.token_env: ожидается имя переменной окружения, например GITLAB_TOKEN")
                elif field == "prerelease_pattern":
                    try:
                        re.compile(value)
                    except re.error:
                        errors.append(f"{path}.prerelease_pattern: некорректное регулярное выражение")
            channel = software.get("channel")
            if isinstance(channel, str) and channel not in {"stable", "prerelease"}:
                errors.append(f"{path}.channel: допустимы stable и prerelease")
            repository = software.get("repository")
            repository_pattern = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
            if provider == "gitlab":
                repository_pattern = r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+"
            if isinstance(repository, str) and (
                not re.fullmatch(repository_pattern, repository)
                or any(part in {".", ".."} for part in repository.split("/"))
            ):
                example = "group/subgroup/project" if provider == "gitlab" else "owner/repository"
                errors.append(f"{path}.repository: ожидается путь {example}, без URL")

    if errors:
        raise ConfigError("Ошибки в config.yaml:\n" + "\n".join(f"- {error}" for error in errors))
    return config
