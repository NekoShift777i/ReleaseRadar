import sqlite3
import secrets
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone, timedelta

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
            """
            INSERT INTO notification_buttons (
                token, software_id, version, created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                token,
                software_id,
                version,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return token


def cleanup_notification_buttons(
    retention: timedelta,
    now: datetime | None = None,
) -> int:
    """Удаляет просроченные кнопки и возвращает их количество."""
    if retention <= timedelta(0):
        raise ValueError("Срок хранения должен быть положительным")

    if now is None:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Время должно содержать часовой пояс")

    cutoff = (now.astimezone(timezone.utc) - retention).isoformat()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM notification_buttons
            WHERE created_at < ?
            """,
            (cutoff,),
        )

        return cursor.rowcount



def get_notification_button(token: str) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            "SELECT software_id, version FROM notification_buttons WHERE token = ?",
            (token,),
        ).fetchone()



def get_valid_notification_button(
    token: str,
    retention: timedelta,
    now: datetime | None = None,
) -> sqlite3.Row | None:
    """Возвращает кнопку, только если срок её действия не истёк."""
    if retention <= timedelta(0):
        raise ValueError("Срок хранения должен быть положительным")

    if now is None:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Время должно содержать часовой пояс")

    with get_connection() as connection:
        button = connection.execute(
            """
            SELECT software_id, version, created_at
            FROM notification_buttons
            WHERE token = ?
            """,
            (token,),
        ).fetchone()

    if button is None:
        return None

    created_at = datetime.fromisoformat(button["created_at"])

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("Время создания кнопки не содержит часовой пояс")

    if now.astimezone(timezone.utc) - created_at.astimezone(timezone.utc) >= retention:
        return None

    return button



def initialize_database() -> None:
    with get_connection() as connection:
        legacy_database = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'notification_buttons'"
        ).fetchone() is None
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_buttons (
            token TEXT PRIMARY KEY,
            software_id TEXT NOT NULL,
            version TEXT NOT NULL,
            created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS software_state (
                software_id TEXT PRIMARY KEY,
                current_version TEXT NOT NULL,
                latest_version TEXT,
                last_notified_version TEXT,
                last_checked_at TEXT,
                last_error TEXT,
                last_error_at TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS skipped_releases (
                software_id TEXT NOT NULL,
                version TEXT NOT NULL,
                reason TEXT NOT NULL,
                skipped_at TEXT NOT NULL,
                PRIMARY KEY (software_id, version)
            )
            """
        )

        button_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(notification_buttons)"
            )
        }

        if "created_at" not in button_columns:
            connection.execute(
                "ALTER TABLE notification_buttons ADD COLUMN created_at TEXT"
            )
            connection.execute(
                """
                UPDATE notification_buttons
                SET created_at = ?
                WHERE created_at IS NULL
                """,
                (datetime.now(timezone.utc).isoformat(),),
            )

        columns = {row["name"] for row in connection.execute("PRAGMA table_info(software_state)")}
        for column in ("last_error", "last_error_at"):
            if column not in columns:
                connection.execute(f"ALTER TABLE software_state ADD COLUMN {column} TEXT")
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
                last_checked_at,
                last_error,
                last_error_at
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
                last_checked_at = ?,
                last_error = NULL,
                last_error_at = NULL
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


def record_software_error(software_id: str, message: str, occurred_at: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE software_state SET last_error = ?, last_error_at = ? WHERE software_id = ?",
            (message, occurred_at, software_id),
        )



def skip_release(
    software_id: str,
    version: str,
    reason: str,
) -> bool:
    reason = reason.strip()

    if not reason:
        raise ValueError("Причина пропуска не может быть пустой")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO skipped_releases (
                software_id,
                version,
                reason,
                skipped_at
            )
            SELECT
                software_id,
                latest_version,
                ?,
                ?
            FROM software_state
            WHERE software_id = ?
              AND latest_version = ?
              AND current_version != ?
            """,
            (
                reason,
                datetime.now(timezone.utc).isoformat(),
                software_id,
                version,
                version,
            ),
        )

        return cursor.rowcount == 1



def is_release_skipped(
    software_id: str,
    version: str,
) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM skipped_releases
            WHERE software_id = ? AND version = ?
            """,
            (software_id, version),
        )

        return row.fetchone() is not None


def get_skipped_releases(
    software_id: str | None = None,
) -> list[dict]:
    """Return skipped releases, newest first."""
    query = """
        SELECT
            software_id,
            version,
            reason,
            skipped_at
        FROM skipped_releases
    """
    params = []

    if software_id is not None:
        query += " WHERE software_id = ?"
        params.append(software_id)

    query += " ORDER BY skipped_at DESC, software_id ASC, version ASC"

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()

    return [dict(row) for row in rows]
