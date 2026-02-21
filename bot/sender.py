"""Send Telegram messages via HTTP API (for background thread)."""
import logging
import queue
import threading
import time

import requests

from bot.message_parser import get_button_label

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _format_message(parsed: dict) -> str:
    lines = [
        f"📧 *От:* {parsed.get('from_addr', '')}",
        f"*Тема:* {parsed.get('subject', '(без темы)')}",
        "",
    ]
    if parsed.get("intro"):
        intro = parsed["intro"][:400]
        lines.append(intro)
        if len(parsed.get("intro", "")) > 400:
            lines.append("...")

    if parsed.get("codes"):
        lines.append("")
        lines.append("*Коды:* " + ", ".join(f"`{c}`" for c in parsed["codes"]))

    return "\n".join(lines)


def _build_reply_markup(urls: list[str], url_labels: dict | None = None) -> dict | None:
    """Build inline keyboard for URLs with smart labels (Activate, Verify, etc.)."""
    if not urls:
        return None
    buttons = []
    for url in urls[:5]:
        label = get_button_label(url, (url_labels or {}).get(url))
        buttons.append([{"text": label, "url": url}])
    return {"inline_keyboard": buttons}


def send_message_sync(token: str, chat_id: str, parsed: dict) -> bool:
    """Send formatted message to Telegram (sync, for background thread)."""
    text = _format_message(parsed)
    reply_markup = _build_reply_markup(parsed.get("urls", []), parsed.get("url_labels"))

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        resp = requests.post(
            TELEGRAM_API.format(token=token),
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("send_message failed: %s", e)
        return False


def run_sender_thread(msg_queue, bot_token: str):
    """Background thread: drain queue and send messages."""
    def worker():
        while True:
            try:
                user_id, parsed = msg_queue.get(timeout=2)
                send_message_sync(bot_token, user_id, parsed)
            except queue.Empty:
                pass
            except Exception as e:
                logger.warning("Sender thread: %s", e)
            time.sleep(0.3)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    logger.info("Sender thread started")
