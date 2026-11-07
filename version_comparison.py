
from enum import Enum

from packaging.version import InvalidVersion, Version


class VersionComparison(Enum):
    NEWER = "newer"
    NOT_NEWER = "not_newer"
    UNKNOWN = "unknown"


def compare_versions(
    current_version: str,
    latest_version: str,
) -> VersionComparison:
    """Сравнивает версии, не угадывая порядок нестандартных обозначений."""

    if not isinstance(current_version, str) or not isinstance(latest_version, str):
        return VersionComparison.UNKNOWN

    current = current_version.strip()
    latest = latest_version.strip()

    if not current or not latest:
        return VersionComparison.UNKNOWN

    if current == latest:
        return VersionComparison.NOT_NEWER

    try:
        parsed_current = Version(current)
        parsed_latest = Version(latest)
    except InvalidVersion:
        return VersionComparison.UNKNOWN

    if parsed_latest > parsed_current:
        return VersionComparison.NEWER

    return VersionComparison.NOT_NEWER
