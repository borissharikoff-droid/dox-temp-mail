"""Background mail checker: concurrent polling with expired-session filtering."""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from bot.mail_service import get_messages, get_message_detail
from bot.message_parser import parse_message
import db
from config import POLL_INTERVAL, SESSION_MAX_AGE_SECONDS, MAX_CONCURRENT_POLLS

logger = logging.getLogger(__name__)

_CLEANUP_EVERY_N_CYCLES = 10


def _is_expired(created_at: str) -> bool:
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() > SESSION_MAX_AGE_SECONDS
    except Exception:
        return True


def _adaptive_interval(session_count: int) -> float:
    if session_count < 100:
        return POLL_INTERVAL
    if session_count < 300:
        return max(POLL_INTERVAL, 45)
    return 60


def _check_new_messages(user_id: str, token: str, on_new) -> bool:
    try:
        messages = get_messages(token)
    except Exception as e:
        logger.warning("get_messages failed for user %s: %s", user_id, e)
        return False

    any_new = False
    for msg in messages:
        msg_id = msg.get("id")
        if not msg_id or not db.claim_message_seen(msg_id):
            continue
        try:
            detail = get_message_detail(token, msg_id)
            parsed = parse_message(msg, detail)
            on_new(user_id, msg_id, parsed)
            any_new = True
        except Exception as e:
            db.unmark_message_seen(msg_id)
            logger.warning("Failed to process message %s: %s", msg_id, e)
    return any_new


def run_mail_checker(on_new_message):
    def worker():
        cycle = 0
        while True:
            cycle += 1
            sessions = db.get_all_sessions()
            active = [s for s in sessions if not _is_expired(s["created_at"])]

            if cycle % _CLEANUP_EVERY_N_CYCLES == 0:
                db.cleanup_expired_sessions()
                db.cleanup_old_messages()

            if not active:
                time.sleep(POLL_INTERVAL)
                continue

            logger.info("Polling %d active sessions (skipped %d expired)",
                        len(active), len(sessions) - len(active))

            with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_POLLS, len(active))) as pool:
                futures = {
                    pool.submit(
                        _check_new_messages,
                        s["user_id"],
                        s["token"],
                        on_new_message,
                    ): s["user_id"]
                    for s in active
                }
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except Exception as e:
                        logger.warning("Poll error for %s: %s", futures[fut], e)

            interval = _adaptive_interval(len(active))
            time.sleep(interval)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    logger.info("Mail checker thread started (poll interval: %ds, max workers: %d)",
                POLL_INTERVAL, MAX_CONCURRENT_POLLS)
