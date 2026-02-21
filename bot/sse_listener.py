"""Background mail checker: polling for new messages (SSE optional, polling is reliable)."""
import logging
import threading
import time

from bot.mail_service import get_messages, get_message_detail
from bot.message_parser import parse_message
import db
from config import POLL_INTERVAL

logger = logging.getLogger(__name__)


def _check_new_messages(user_id: str, token: str, on_new) -> bool:
    """
    Fetch messages, find unseen ones, send to callback. Returns True if any new.
    """
    try:
        messages = get_messages(token)
    except Exception as e:
        logger.warning("get_messages failed for user %s: %s", user_id, e)
        return False

    any_new = False
    for msg in messages:
        msg_id = msg.get("id")
        if not msg_id or db.is_message_seen(msg_id):
            continue
        try:
            detail = get_message_detail(token, msg_id)
            parsed = parse_message(msg, detail)
            on_new(user_id, msg_id, parsed)
            db.mark_message_seen(msg_id)
            any_new = True
        except Exception as e:
            logger.warning("Failed to process message %s: %s", msg_id, e)
    return any_new


def run_mail_checker(on_new_message):
    """
    Background thread: poll each session for new messages.
    on_new_message(user_id, msg_id, parsed)
    """
    def worker():
        while True:
            sessions = db.get_all_sessions()
            for session in sessions:
                try:
                    _check_new_messages(
                        session["user_id"],
                        session["token"],
                        on_new_message,
                    )
                except Exception as e:
                    logger.exception("Error checking account: %s", e)
            time.sleep(POLL_INTERVAL)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    logger.info("Mail checker thread started (poll interval: %ds)", POLL_INTERVAL)
