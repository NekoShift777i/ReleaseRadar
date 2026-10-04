import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit, parse_qs

import httpx

from providers.base import Release, raise_if_stopping
from threading import Event

logger = logging.getLogger(__name__)
DEFAULT_PRERELEASE_PATTERN = r"(?i)(?:^|[._-])(?:alpha|beta|rc|pre|preview|dev|snapshot)(?:[._-]?\d+)*(?=$|[._-])"


def get_latest_release(
    repository: str,
    include_prerelease: bool = False,
    *,
    base_url: str = "https://gitlab.com",
    token_env: str | None = None,
    prerelease_pattern: str = DEFAULT_PRERELEASE_PATTERN,
    stop_event: Event | None = None,
) -> Release:
    """Select the first published release in released_at descending order."""
    base_url = base_url.rstrip("/")
    endpoint = f"{base_url}/api/v4/projects/{quote(repository, safe='')}/releases"
    headers = {"Accept": "application/json"}
    if token_env:
        token = os.getenv(token_env)
        if not token or not token.strip():
            raise ValueError(f"GitLab token environment variable {token_env} is not configured")
        headers["PRIVATE-TOKEN"] = token

    pattern = re.compile(prerelease_pattern)
    now = datetime.now(timezone.utc)
    url = endpoint
    params = {"order_by": "released_at", "sort": "desc", "per_page": 100, "page": 1}
    visited = set()
    logger.info("Checking GitLab releases for %s (server=%s, include_prerelease=%s)", repository, base_url, include_prerelease)

    for page in range(100):
        raise_if_stopping(stop_event)
        current_page = int(params["page"]) if params else int(parse_qs(urlsplit(url).query).get("page", [1])[0])
        request_key = (url, tuple(sorted(params.items())) if params else ())
        if request_key in visited:
            raise ValueError("GitLab returned a pagination loop")
        visited.add(request_key)
        response = httpx.get(url, params=params, headers=headers, timeout=10.0)
        raise_if_stopping(stop_event)
        response.raise_for_status()
        releases = response.json()
        if not isinstance(releases, list):
            raise ValueError("GitLab Releases API returned an invalid response")
        if not releases:
            break
        for data in releases:
            raise_if_stopping(stop_event)
            if not isinstance(data, dict):
                raise ValueError("GitLab returned an invalid release")
            if data.get("upcoming_release"):
                continue
            released_at = data.get("released_at")
            if not isinstance(released_at, str):
                raise ValueError("GitLab release has no released_at timestamp")
            released = datetime.fromisoformat(released_at.replace("Z", "+00:00"))
            if released.tzinfo is None:
                released = released.replace(tzinfo=timezone.utc)
            if released > now:
                continue
            version = data.get("tag_name")
            if not isinstance(version, str) or not version.strip():
                raise ValueError("GitLab release has no tag_name")
            prerelease = bool(pattern.search(version))
            if prerelease and not include_prerelease:
                continue
            links = data.get("_links") or {}
            release_url = links.get("self") if isinstance(links, dict) else None
            if not isinstance(release_url, str) or not release_url:
                release_url = f"{base_url}/{quote(repository, safe='/')}/-/releases/{quote(version, safe='')}"
            logger.info("Latest release for %s: %s (prerelease=%s)", repository, version, prerelease)
            return Release(version=version, url=release_url, prerelease=prerelease)

        next_url = response.links.get("next", {}).get("url")
        if next_url:
            expected, actual = urlsplit(endpoint), urlsplit(next_url)
            if (actual.scheme, actual.netloc, actual.path) != (expected.scheme, expected.netloc, expected.path):
                raise ValueError("GitLab returned an unexpected pagination URL")
            url, params = next_url, None
        else:
            next_page = response.headers.get("x-next-page")
            if next_page:
                if not next_page.isdigit() or int(next_page) <= current_page:
                    raise ValueError("GitLab returned an invalid next page")
                params = {"order_by": "released_at", "sort": "desc", "per_page": 100, "page": int(next_page)}
                url = endpoint
            elif len(releases) == 100 and next_page is None:
                # Some GitLab.com pagination headers can be omitted.
                url = endpoint
                params = {"order_by": "released_at", "sort": "desc", "per_page": 100, "page": current_page + 1}
            else:
                break
    else:
        raise ValueError("GitLab release search exceeded 100 pages")
    raise ValueError(f"No published releases match the selected channel for {repository}")
