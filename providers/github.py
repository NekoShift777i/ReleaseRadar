from providers.base import Release, CheckCancelled, raise_if_stopping
from threading import Event

import httpx
import logging

GITHUB_API_URL = "https://api.github.com"

logger = logging.getLogger(__name__)




def get_latest_release(
    repository:str,
    include_prerelease: bool = False,
    *,
    stop_event: Event | None = None,
) -> Release:
    raise_if_stopping(stop_event)
    logger.info(
        "Checking GitHub releases for %s "
        "(include_prerelease=%s)",
        repository,
        include_prerelease,
    )

    if include_prerelease:
        url = f"{GITHUB_API_URL}/repos/{repository}/releases"
    else:
        url = f"{GITHUB_API_URL}/repos/{repository}/releases/latest"

    try:
        response = httpx.get(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10.0,
        )
        raise_if_stopping(stop_event)
        response.raise_for_status()

        data = response.json()

        if include_prerelease:
            release_data = next (
                release
                for release in data 
                if not release["draft"]
            )
        else:
            release_data =data

        release = Release(
            version=release_data["tag_name"],
            url=release_data["html_url"],
            prerelease=release_data["prerelease"],
        )

        logger.info(
            "Latest release for %s: %s (prerelease=%s)",
            repository,
            release.version,
            release.prerelease,
        )

        return release

    except CheckCancelled:
        raise
    except Exception:
        logger.exception(
            "Failed to get GitHub release for %s",
            repository,
        )
        raise
