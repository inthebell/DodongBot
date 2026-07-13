import hashlib
import sqlite3
from pathlib import Path


DB_PATH = Path("market.db")


def create_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_message_id TEXT UNIQUE,
            trade_hash TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total_price INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            trade_date TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    migrate_old_table(connection)

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_trades_discord_message_id
        ON trades(discord_message_id)
        WHERE discord_message_id IS NOT NULL
        """
    )

    connection.commit()
    return connection


def migrate_old_table(
    connection: sqlite3.Connection,
) -> None:
    columns = connection.execute(
        "PRAGMA table_info(trades)"
    ).fetchall()

    column_names = {
        column[1]
        for column in columns
    }

    if "discord_message_id" not in column_names:
        connection.execute(
            """
            ALTER TABLE trades
            ADD COLUMN discord_message_id TEXT
            """
        )

    table_sql_row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'trades'
        """
    ).fetchone()

    if table_sql_row is None:
        return

    table_sql = table_sql_row[0] or ""

    if "trade_hash TEXT NOT NULL UNIQUE" not in table_sql:
        return

    connection.execute(
        """
        CREATE TABLE trades_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_message_id TEXT UNIQUE,
            trade_hash TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total_price INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            trade_date TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    connection.execute(
        """
        INSERT INTO trades_new (
            id,
            discord_message_id,
            trade_hash,
            item_name,
            quantity,
            total_price,
            unit_price,
            trade_date,
            raw_text,
            created_at
        )
        SELECT
            id,
            discord_message_id,
            trade_hash,
            item_name,
            quantity,
            total_price,
            unit_price,
            trade_date,
            raw_text,
            created_at
        FROM trades
        """
    )

    connection.execute(
        """
        DROP TABLE trades
        """
    )

    connection.execute(
        """
        ALTER TABLE trades_new
        RENAME TO trades
        """
    )


def make_trade_hash(trade: dict) -> str:
    source = "|".join(
        [
            trade["item_name"],
            str(trade["quantity"]),
            str(trade["total"]),
            trade["trade_date"].strftime(
                "%Y-%m-%d %H:%M"
            ),
            trade["raw_text"],
        ]
    )

    return hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()


def save_trade(
    connection: sqlite3.Connection,
    trade: dict,
    discord_message_id: str,
) -> bool:
    trade_hash = make_trade_hash(trade)

    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO trades (
            discord_message_id,
            trade_hash,
            item_name,
            quantity,
            total_price,
            unit_price,
            trade_date,
            raw_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            discord_message_id,
            trade_hash,
            trade["item_name"],
            trade["quantity"],
            trade["total"],
            trade["unit_price"],
            trade["trade_date"].strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            trade["raw_text"],
        ),
    )

    connection.commit()

    return cursor.rowcount == 1


def message_exists(
    connection: sqlite3.Connection,
    discord_message_id: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM trades
        WHERE discord_message_id = ?
        LIMIT 1
        """,
        (
            discord_message_id,
        ),
    ).fetchone()

    return row is not None