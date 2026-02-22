"""SQLite database for sessions and seen messages."""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

from config import SESSION_MAX_AGE_SECONDS

DB_PATH = Path(__file__).parent / "data" / "bot.db"


def _ensure_db_dir():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection():
    _ensure_db_dir()
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                token TEXT NOT NULL,
                account_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages_seen (
                message_id TEXT PRIMARY KEY,
                seen_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS ui_state (
                user_id TEXT PRIMARY KEY,
                last_message_id INTEGER NOT NULL
            );
        """)
        conn.commit()
        _migrate(conn)
        cleanup_expired_sessions(conn)
        cleanup_old_messages(conn)
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection):
    """Add seen_at column if missing (migration from older schema)."""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(messages_seen)").fetchall()]
    if "seen_at" not in cols:
        conn.execute("ALTER TABLE messages_seen ADD COLUMN seen_at TEXT NOT NULL DEFAULT ''")
        conn.commit()


def save_session(user_id: str, email: str, token: str, account_id: str):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (user_id, email, token, account_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, email, token, account_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_session(user_id: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT user_id, email, token, account_id, created_at FROM sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_session(user_id: str):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def is_message_seen(message_id: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM messages_seen WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def mark_message_seen(message_id: str):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO messages_seen (message_id, seen_at) VALUES (?, ?)",
            (message_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def claim_message_seen(message_id: str) -> bool:
    """
    Atomically claim a message for processing.
    Returns True only for the first caller.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO messages_seen (message_id, seen_at) VALUES (?, ?)",
            (message_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def unmark_message_seen(message_id: str):
    """Remove seen marker (used when processing failed after claim)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM messages_seen WHERE message_id = ?", (message_id,))
        conn.commit()
    finally:
        conn.close()


def get_all_sessions() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT user_id, email, token, account_id, created_at FROM sessions"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_last_ui_message_id(user_id: str) -> int | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT last_message_id FROM ui_state WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return int(row["last_message_id"]) if row else None
    finally:
        conn.close()


def set_last_ui_message_id(user_id: str, message_id: int):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO ui_state (user_id, last_message_id) VALUES (?, ?)",
            (user_id, int(message_id)),
        )
        conn.commit()
    finally:
        conn.close()


def clear_last_ui_message_id(user_id: str):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM ui_state WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


# ── Cleanup ────────────────────────────────────────────────────────

def cleanup_expired_sessions(conn: sqlite3.Connection | None = None):
    """Delete sessions older than SESSION_MAX_AGE_SECONDS."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=SESSION_MAX_AGE_SECONDS)).isoformat()
        deleted = conn.execute(
            "DELETE FROM sessions WHERE created_at < ?", (cutoff,)
        ).rowcount
        conn.commit()
        if deleted:
            from logging import getLogger
            getLogger(__name__).info("Cleaned up %d expired sessions", deleted)
    finally:
        if own:
            conn.close()


def cleanup_old_messages(conn: sqlite3.Connection | None = None, days: int = 7):
    """Delete seen-message records older than `days` days."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        deleted = conn.execute(
            "DELETE FROM messages_seen WHERE seen_at != '' AND seen_at < ?", (cutoff,)
        ).rowcount
        conn.commit()
        if deleted:
            from logging import getLogger
            getLogger(__name__).info("Cleaned up %d old message records", deleted)
    finally:
        if own:
            conn.close()
