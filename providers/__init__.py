from providers import github, gitlab
from providers.base import Release
from threading import Event


def get_latest_release(software: dict, *, stop_event: Event | None = None) -> Release:
    include_prerelease = software["channel"] == "prerelease"
    provider = software["provider"]
    stop_options = {"stop_event": stop_event} if stop_event is not None else {}
    if provider == "github":
        return github.get_latest_release(software["repository"], include_prerelease, **stop_options)
    if provider == "gitlab":
        return gitlab.get_latest_release(
            software["repository"], include_prerelease,
            base_url=software.get("gitlab_url", "https://gitlab.com"),
            token_env=software.get("token_env"),
            prerelease_pattern=software.get("prerelease_pattern", gitlab.DEFAULT_PRERELEASE_PATTERN),
            **stop_options,
        )
    raise ValueError(f"Unsupported provider: {provider}")
