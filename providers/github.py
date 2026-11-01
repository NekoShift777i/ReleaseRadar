from providers.base import Release, CheckCancelled, raise_if_stopping
from threading import Event

import httpx
import logging
import os
from packaging.version import Version, InvalidVersion

GITHUB_API_URL = "https://api.github.com"
logger = logging.getLogger(__name__)


def _version(tag: str) -> Version | None:
    try:
        return Version(tag.strip().removeprefix('v').removeprefix('V'))
    except InvalidVersion:
        return None



def _is_allowed_release(
    item: dict,
    include_prerelease: bool,
    release_filter: str,
) -> bool:
    if item.get("draft"):
        return False

    if include_prerelease:
        return True

    github_prerelease = bool(item.get("prerelease"))
    version = _version(item.get("tag_name", ""))
    version_prerelease = version.is_prerelease if version is not None else False

    if release_filter == "github":
        return not github_prerelease

    if release_filter == "version":
        return not version_prerelease

    return not github_prerelease and not version_prerelease


def get_latest_release(
    repository: str,
    include_prerelease: bool = False,
    *,
    release_filter: str = "strict",
    stop_event: Event | None = None,
) -> Release:
    raise_if_stopping(stop_event)
    logger.info("Checking GitHub releases for %s (include_prerelease=%s)", repository, include_prerelease)
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if release_filter not in {"strict", "github", "version"}:
        raise ValueError(f"Неизвестный режим фильтрации выпусков: {release_filter}")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        # GitHub sorts releases by publication, not by semantic version.
        # Fetch all pages so a recently updated older branch cannot win.
        candidates: list[dict] = []
        page = 1
        with httpx.Client(timeout=10.0, headers=headers) as client:
            while True:
                raise_if_stopping(stop_event)
                response = client.get(
                    f"{GITHUB_API_URL}/repos/{repository}/releases",
                    params={"per_page": 100, "page": page},
                )
                raise_if_stopping(stop_event)
                if token and response.status_code == 401:
                    raise RuntimeError("GitHub отклонил GITHUB_TOKEN (HTTP 401). Проверьте ключ в .env.")
                if response.status_code in (403, 429) and response.headers.get("X-RateLimit-Remaining") == "0":
                    raise RuntimeError(f"Превышен лимит запросов GitHub API (HTTP {response.status_code}).")
                response.raise_for_status()
                batch = response.json()
                if not isinstance(batch, list):
                    raise RuntimeError("GitHub вернул неожиданный формат списка выпусков")
                candidates.extend(
                    item for item in batch
                    if _is_allowed_release(
                        item,
                        include_prerelease,
                        release_filter,
                    )
                )
                if len(batch) < 100:
                    break
                page += 1

        if not candidates:
            raise RuntimeError(f"Не найдены подходящие выпуски GitHub: {repository}")

        comparable = [(version, item) for item in candidates
                      if (version := _version(item.get("tag_name", ""))) is not None]
        if comparable:
            _, chosen = max(comparable, key=lambda pair: pair[0])
        else:
            # Non-version tags: retain GitHub's newest-published order.
            chosen = candidates[0]
            logger.warning("No comparable version tags for %s; using newest published release", repository)

        release = Release(
            version=chosen["tag_name"],
            url=chosen["html_url"],
            prerelease=bool(chosen.get("prerelease")),
        )
        logger.info("Latest release for %s: %s (prerelease=%s)", repository, release.version, release.prerelease)
        return release
    except CheckCancelled:
        raise
    except Exception:
        logger.exception("Failed to get GitHub release for %s", repository)
        raise
