from dataclasses import dataclass
from packaging.version import Version, InvalidVersion



@dataclass
class UpdateResult:
    software_id: str
    software_name: str
    current_version: str
    latest_version: str
    release_url: str
    update_available: bool
    notify_required: bool

def is_newer_version(current_version: str, latest_version: str) -> bool:
    try:
        return Version(latest_version.lstrip("vV")) > Version(current_version.lstrip("vV"))
    except InvalidVersion:
        # Preserve existing behavior for projects using nonstandard tags.
        return current_version != latest_version


def should_notify(
        current_version: str,
        latest_version: str,
        last_notified_version: str | None,
) -> bool:
    return (
        is_newer_version(current_version, latest_version)
        and last_notified_version != latest_version
    )