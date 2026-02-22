"""Send Telegram messages via HTTP API (for background thread)."""
import logging
import queue
import threading
import time

from bot.media_style import send_message_with_gif_sync
from bot.message_parser import get_button_label

logger = logging.getLogger(__name__)


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
    ok = send_message_with_gif_sync(
        token=token,
        chat_id=chat_id,
        tag="new_mail",
        text=text,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    if not ok:
        logger.warning("send_message failed")
    return ok


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
