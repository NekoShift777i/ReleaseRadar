from dataclasses import dataclass



@dataclass
class UpdateResult:
    software_id: str
    software_name: str
    current_version: str
    latest_version: str
    release_url: str
    update_available: bool
    notify_required: bool

def should_notify(
        current_version: str,
        latest_version: str,
        last_notified_version: str | None,
) -> bool:
    return (
        current_version != latest_version
        and last_notified_version != latest_version
    )