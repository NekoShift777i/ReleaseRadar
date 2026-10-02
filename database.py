import sqlite3

from pathlib import Path



DATABASE_PATH = Path("release-radar.db")



def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    return connection



def initialize_database() -> None:
    with get_connection() as connection:
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



def mark_version_updated(software_id:str) -> None:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE software_state
            SET current_version = latest_version
            WHERE software_id = ?
              AND latest_version IS NOT NULL
            """,
            (software_id,),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"Cannot mark (software_id) as updated: "
                "software not found or latest version is NULL" \
            )