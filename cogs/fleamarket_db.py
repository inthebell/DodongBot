import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DB_PATH = (
    Path(__file__).resolve().parent.parent
    / "fleamarket.db"
)

KST = timezone(timedelta(hours=9))
ACTIVE_DAYS = 3


def get_kst_now_dt() -> datetime:
    return datetime.now(KST)


def get_kst_now() -> str:
    return get_kst_now_dt().isoformat(timespec="seconds")


def get_expiration_time() -> str:
    return (
        get_kst_now_dt() + timedelta(days=ACTIVE_DAYS)
    ).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def create_database() -> None:
    connection = connect()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS flea_market (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                keywords TEXT NOT NULL,
                description TEXT NOT NULL,
                waypoint TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                approved_at TEXT,
                expires_at TEXT,
                views INTEGER NOT NULL DEFAULT 0,
                approval_channel_id INTEGER,
                approval_message_id INTEGER,
                reviewed_at TEXT,
                reviewed_by INTEGER,
                revision_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        cursor.execute("PRAGMA table_info(flea_market)")
        columns = {
            row["name"]
            for row in cursor.fetchall()
        }

        additions = {
            "category": "TEXT NOT NULL DEFAULT ''",
            "approved_at": "TEXT",
            "expires_at": "TEXT",
            "approval_channel_id": "INTEGER",
            "approval_message_id": "INTEGER",
            "reviewed_at": "TEXT",
            "reviewed_by": "INTEGER",
            "revision_count": "INTEGER NOT NULL DEFAULT 0",
        }

        for column_name, definition in additions.items():
            if column_name not in columns:
                cursor.execute(
                    f"ALTER TABLE flea_market "
                    f"ADD COLUMN {column_name} {definition}"
                )

        connection.commit()

    finally:
        connection.close()


def expire_ads() -> int:
    connection = connect()

    try:
        cursor = connection.execute(
            """
            UPDATE flea_market
            SET status = 'expired'
            WHERE status = 'active'
              AND expires_at IS NOT NULL
              AND expires_at <= ?
            """,
            (get_kst_now(),),
        )
        connection.commit()
        return cursor.rowcount

    finally:
        connection.close()


def has_existing_ad(
    guild_id: int,
    user_id: int,
    market_type: str,
) -> bool:
    expire_ads()
    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT id
            FROM flea_market
            WHERE guild_id = ?
              AND user_id = ?
              AND type = ?
              AND status IN ('pending', 'active')
            LIMIT 1
            """,
            (guild_id, user_id, market_type),
        ).fetchone()

        return row is not None

    finally:
        connection.close()


def create_ad(
    *,
    guild_id: int,
    user_id: int,
    market_type: str,
    category: str,
    keywords: str,
    description: str,
    waypoint: str,
) -> int:
    connection = connect()

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO flea_market (
                guild_id,
                user_id,
                type,
                category,
                keywords,
                description,
                waypoint,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                guild_id,
                user_id,
                market_type,
                category,
                keywords,
                description,
                waypoint,
                get_kst_now(),
            ),
        )

        ad_id = int(cursor.lastrowid)
        connection.commit()
        return ad_id

    finally:
        connection.close()


def delete_ad(ad_id: int) -> None:
    connection = connect()

    try:
        connection.execute(
            "DELETE FROM flea_market WHERE id = ?",
            (ad_id,),
        )
        connection.commit()

    finally:
        connection.close()


def get_ad(ad_id: int) -> dict[str, Any] | None:
    expire_ads()
    connection = connect()

    try:
        row = connection.execute(
            "SELECT * FROM flea_market WHERE id = ?",
            (ad_id,),
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def get_user_ad(
    *,
    guild_id: int,
    user_id: int,
    market_type: str,
) -> dict[str, Any] | None:
    expire_ads()
    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT *
            FROM flea_market
            WHERE guild_id = ?
              AND user_id = ?
              AND type = ?
              AND status IN ('pending', 'active')
            ORDER BY id DESC
            LIMIT 1
            """,
            (guild_id, user_id, market_type),
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def get_user_ads(
    *,
    guild_id: int,
    user_id: int,
) -> list[dict[str, Any]]:
    expire_ads()
    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM flea_market
            WHERE guild_id = ?
              AND user_id = ?
              AND status IN ('pending', 'active')
            ORDER BY id DESC
            """,
            (guild_id, user_id),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()

def get_management_ads() -> list[dict[str, Any]]:
    expire_ads()
    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM flea_market
            WHERE status IN ('pending', 'active')
            ORDER BY
                CASE status
                    WHEN 'pending' THEN 0
                    WHEN 'active' THEN 1
                    ELSE 2
                END,
                CASE
                    WHEN expires_at IS NULL THEN created_at
                    ELSE expires_at
                END ASC,
                id DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()

def get_pending_ads() -> list[dict[str, Any]]:
    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM flea_market
            WHERE status = 'pending'
              AND approval_channel_id IS NOT NULL
              AND approval_message_id IS NOT NULL
            ORDER BY id ASC
            """
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def set_approval_message(
    ad_id: int,
    channel_id: int,
    message_id: int,
) -> None:
    connection = connect()

    try:
        connection.execute(
            """
            UPDATE flea_market
            SET approval_channel_id = ?,
                approval_message_id = ?
            WHERE id = ?
            """,
            (channel_id, message_id, ad_id),
        )
        connection.commit()

    finally:
        connection.close()


def update_pending_ad(
    *,
    ad_id: int,
    category: str,
    keywords: str,
    description: str,
    waypoint: str,
) -> bool:
    connection = connect()

    try:
        cursor = connection.execute(
            """
            UPDATE flea_market
            SET category = ?,
                keywords = ?,
                description = ?,
                waypoint = ?
            WHERE id = ?
              AND status = 'pending'
            """,
            (
                category,
                keywords,
                description,
                waypoint,
                ad_id,
            ),
        )
        connection.commit()
        return cursor.rowcount > 0

    finally:
        connection.close()


def update_user_ad_for_review(
    *,
    ad_id: int,
    user_id: int,
    category: str,
    keywords: str,
    description: str,
    waypoint: str,
) -> tuple[bool, bool]:
    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT status
            FROM flea_market
            WHERE id = ?
              AND user_id = ?
              AND status IN ('pending', 'active')
            """,
            (ad_id, user_id),
        ).fetchone()

        if row is None:
            return False, False

        was_active = row["status"] == "active"

        cursor = connection.execute(
            """
            UPDATE flea_market
            SET category = ?,
                keywords = ?,
                description = ?,
                waypoint = ?,
                status = 'pending',
                reviewed_at = NULL,
                reviewed_by = NULL,
                revision_count = revision_count + ?
            WHERE id = ?
              AND user_id = ?
              AND status IN ('pending', 'active')
            """,
            (
                category,
                keywords,
                description,
                waypoint,
                1 if was_active else 0,
                ad_id,
                user_id,
            ),
        )
        connection.commit()
        return cursor.rowcount > 0, was_active

    finally:
        connection.close()


def approve_ad(
    *,
    ad_id: int,
    reviewer_id: int,
) -> bool:
    now = get_kst_now()
    new_expires_at = get_expiration_time()
    connection = connect()

    try:
        cursor = connection.execute(
            """
            UPDATE flea_market
            SET status = 'active',
                approved_at = CASE
                    WHEN approved_at IS NULL THEN ?
                    ELSE approved_at
                END,
                expires_at = CASE
                    WHEN expires_at IS NULL THEN ?
                    ELSE expires_at
                END,
                reviewed_at = ?,
                reviewed_by = ?
            WHERE id = ?
              AND status = 'pending'
            """,
            (
                now,
                new_expires_at,
                now,
                reviewer_id,
                ad_id,
            ),
        )
        connection.commit()
        return cursor.rowcount > 0

    finally:
        connection.close()


def reject_ad(
    *,
    ad_id: int,
    reviewer_id: int,
) -> bool:
    connection = connect()

    try:
        cursor = connection.execute(
            """
            UPDATE flea_market
            SET status = 'rejected',
                reviewed_at = ?,
                reviewed_by = ?,
                approved_at = NULL,
                expires_at = NULL
            WHERE id = ?
              AND status = 'pending'
            """,
            (
                get_kst_now(),
                reviewer_id,
                ad_id,
            ),
        )
        connection.commit()
        return cursor.rowcount > 0

    finally:
        connection.close()


def cancel_ad_by_owner(
    *,
    ad_id: int,
    reviewer_id: int,
) -> bool:
    connection = connect()

    try:
        cursor = connection.execute(
            """
            UPDATE flea_market
            SET status = 'cancelled',
                reviewed_at = ?,
                reviewed_by = ?,
                expires_at = NULL
            WHERE id = ?
              AND status IN ('pending', 'active')
            """,
            (
                get_kst_now(),
                reviewer_id,
                ad_id,
            ),
        )
        connection.commit()
        return cursor.rowcount > 0

    finally:
        connection.close()


def delete_user_ad(
    *,
    ad_id: int,
    user_id: int,
) -> bool:
    connection = connect()

    try:
        cursor = connection.execute(
            """
            UPDATE flea_market
            SET status = 'deleted',
                expires_at = NULL
            WHERE id = ?
              AND user_id = ?
              AND status IN ('pending', 'active')
            """,
            (ad_id, user_id),
        )
        connection.commit()
        return cursor.rowcount > 0

    finally:
        connection.close()


def normalize_search_text(value: str) -> str:
    return "".join(value.lower().split())


def search_active_ads(
    *,
    guild_id: int,
    search_term: str,
) -> dict[str, list[dict[str, Any]]]:
    expire_ads()
    normalized_term = normalize_search_text(search_term)
    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM flea_market
            WHERE status = 'active'
              AND expires_at IS NOT NULL
              AND expires_at > ?
            ORDER BY id DESC
            """,
            (get_kst_now(),),
        ).fetchall()

        results: dict[str, list[dict[str, Any]]] = {
            "판매": [],
            "구매": [],
        }

        for row in rows:
            ad = dict(row)
            categories = [
                item.strip()
                for item in ad["category"].split(",")
                if item.strip()
            ]
            keywords = [
                item.strip()
                for item in ad["keywords"].split(",")
                if item.strip()
            ]

            searchable_items = categories + keywords

            if any(
                normalized_term in normalize_search_text(item)
                for item in searchable_items
            ):
                market_type = ad["type"]
                if market_type in results:
                    results[market_type].append(ad)

        return results

    finally:
        connection.close()
