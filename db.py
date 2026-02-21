"""SQLite database for sessions and seen messages."""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "data" / "bot.db"


def _ensure_db_dir():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection():
    _ensure_db_dir()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
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
                message_id TEXT PRIMARY KEY
            );
        """)
        conn.commit()
    finally:
        conn.close()


def save_session(user_id: str, email: str, token: str, account_id: str):
    """Save or replace user session."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO sessions (user_id, email, token, account_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, email, token, account_id, datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_session(user_id: str) -> dict | None:
    """Get session by user_id."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT user_id, email, token, account_id, created_at FROM sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def delete_session(user_id: str):
    """Delete user session."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def is_message_seen(message_id: str) -> bool:
    """Check if message was already sent to user."""
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
    """Mark message as seen."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO messages_seen (message_id) VALUES (?)",
            (message_id,),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_sessions() -> list[dict]:
    """Get all active sessions (for SSE/polling)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT user_id, email, token, account_id, created_at FROM sessions"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
