from dataclasses import dataclass
from version_comparison import VersionComparison, compare_versions



@dataclass
class UpdateResult:
    software_id: str
    software_name: str
    current_version: str
    latest_version: str
    release_url: str
    update_available: bool
    notify_required: bool


def is_newer_version(
    current_version: str,
    latest_version: str,
) -> bool:
    return (
        compare_versions(current_version, latest_version)
        is VersionComparison.NEWER
    )



def should_notify(
        current_version: str,
        latest_version: str,
        last_notified_version: str | None,
) -> bool:
    return (
        is_newer_version(current_version, latest_version)
        and last_notified_version != latest_version
    )