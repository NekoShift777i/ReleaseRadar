import sqlite3
import secrets
from contextlib import contextmanager
from collections.abc import Iterator

from pathlib import Path



DATABASE_PATH = Path("release-radar.db")



@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        with connection:
            yield connection
    finally:
        connection.close()



def create_notification_button(software_id: str, version: str) -> str:
    token = secrets.token_hex(16)
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO notification_buttons (token, software_id, version) VALUES (?, ?, ?)",
            (token, software_id, version),
        )
    return token


def get_notification_button(token: str) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            "SELECT software_id, version FROM notification_buttons WHERE token = ?",
            (token,),
        ).fetchone()


def initialize_database() -> None:
    with get_connection() as connection:
        legacy_database = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'notification_buttons'"
        ).fetchone() is None
        connection.execute(
            "CREATE TABLE IF NOT EXISTS notification_buttons ("
            "token TEXT PRIMARY KEY, software_id TEXT NOT NULL, version TEXT NOT NULL)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS software_state (
                software_id TEXT PRIMARY KEY,
                current_version TEXT NOT NULL,
                latest_version TEXT,
                last_notified_version TEXT,
                last_checked_at TEXT
            )
            """
        )
        if legacy_database:
            # Reissue outstanding legacy notifications with version-bound buttons.
            connection.execute(
                "UPDATE software_state SET last_notified_version = NULL "
                "WHERE latest_version IS NOT NULL AND current_version != latest_version"
            )



def get_software_state(
        software_id: str,
) -> sqlite3.Row | None:
    with get_connection() as connection:
        state = connection.execute(
            """
            SELECT
                software_id,
                current_version,
                latest_version,
                last_notified_version,
                last_checked_at
            FROM software_state
            WHERE software_id = ?
            """,
            (software_id,),
        ).fetchone()

    return state



def create_software_state(
        software_id: str,
        current_version: str,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO software_state (
                software_id,
                current_version
            )
            VALUES (?, ?)
            """,
            (
                software_id,
                current_version,
            ),
        )



def get_or_create_software_state(
        software_id: str,
        current_version: str,
) -> sqlite3.Row:
    state = get_software_state(software_id)

    if state is None:
        create_software_state(
            software_id,
            current_version,
        )

        state = get_software_state(software_id)

    if state is None:
        raise RuntimeError(
            f"Failed to create state for {software_id}"
        )

    return state



def update_software_check(
        software_id: str,
        latest_version: str,
        last_checked_at: str,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE software_state
            SET
                latest_version = ?,
                last_checked_at = ?
            WHERE software_id = ?
            """,
            (
                latest_version,
                last_checked_at,
                software_id,
            ),
        )



def mark_version_updated(software_id: str, version: str) -> bool:
    """Confirm only the release attached to the button, atomically."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE software_state
            SET current_version = ?
            WHERE software_id = ? AND latest_version = ? AND current_version != ?
            """,
            (version, software_id, version, version),
        )
        return cursor.rowcount == 1


def mark_version_notified(
        software_id: str,
        version: str,
) -> None:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE software_state
            SET last_notified_version = ?
            WHERE software_id = ?
            """,
            (
                version,
                software_id,
            ),  
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"Cannot mark {software_id} as notified: "
                "software not found"
            )
