
import logging
from collections.abc import Sequence

from packaging.version import InvalidVersion, Version

from providers.base import Release

logger = logging.getLogger(__name__)


def select_latest_release(
    releases: Sequence[Release],
    *,
    include_prerelease: bool = False,
    selection_mode: str = "version",
) -> Release:
    """Выбирает выпуск из списка, упорядоченного по дате публикации."""

    if selection_mode not in {"version", "published"}:
        raise ValueError(
            f"Неизвестный способ выбора выпуска: {selection_mode}"
        )

    candidates = [
        release
        for release in releases
        if include_prerelease or not release.prerelease
    ]

    if not candidates:
        raise ValueError("Не найдены подходящие выпуски")

    if selection_mode == "published":
        return candidates[0]

    comparable = []

    for release in candidates:
        try:
            version = Version(release.version.strip())
        except InvalidVersion:
            continue

        comparable.append((version, release))

    if comparable:
        return max(comparable, key=lambda item: item[0])[1]

    logger.warning(
        "Не удалось сравнить номера выпусков; "
        "выбран первый опубликованный выпуск"
    )
    return candidates[0]
