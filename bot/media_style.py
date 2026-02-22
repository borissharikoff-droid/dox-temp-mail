"""GIF style helpers (Telegram file_id based)."""
import logging

import requests

from config import GIF_DEFAULT_FILE_ID, GIF_FILE_IDS

logger = logging.getLogger(__name__)

TELEGRAM_ANIMATION_API = "https://api.telegram.org/bot{token}/sendAnimation"


def pick_gif(tag: str) -> str:
    """Pick file_id for a tag, fallback to default."""
    return GIF_FILE_IDS.get(tag) or GIF_DEFAULT_FILE_ID


async def send_gif(bot, chat_id: str | int, tag: str) -> bool:
    """
    Send GIF via PTB bot using Telegram file_id.
    Returns False silently if no file_id configured.
    """
    file_id = pick_gif(tag)
    if not file_id:
        return False
    try:
        await bot.send_animation(chat_id=chat_id, animation=file_id)
        return True
    except Exception as e:
        logger.warning("send_gif failed (tag=%s): %s", tag, e)
        return False


def send_gif_sync(token: str, chat_id: str | int, tag: str) -> bool:
    """
    Send GIF via plain Telegram HTTP API (for sender thread).
    Returns False silently if no file_id configured.
    """
    file_id = pick_gif(tag)
    if not file_id:
        return False
    try:
        resp = requests.post(
            TELEGRAM_ANIMATION_API.format(token=token),
            json={"chat_id": chat_id, "animation": file_id},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("send_gif_sync failed (tag=%s): %s", tag, e)
        return False
