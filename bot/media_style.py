"""GIF style helpers (Telegram file_id / URL based)."""
import logging

import requests

from config import GIF_DEFAULT_FILE_ID, GIF_DEFAULT_URL, GIF_FILE_IDS, GIF_URLS

logger = logging.getLogger(__name__)

TELEGRAM_ANIMATION_API = "https://api.telegram.org/bot{token}/sendAnimation"
TELEGRAM_MESSAGE_API = "https://api.telegram.org/bot{token}/sendMessage"


def pick_gif(tag: str) -> str:
    """Pick animation reference for a tag, fallback to file_id or URL."""
    return (
        GIF_FILE_IDS.get(tag)
        or GIF_DEFAULT_FILE_ID
        or GIF_URLS.get(tag)
        or GIF_DEFAULT_URL
    )


async def send_gif(bot, chat_id: str | int, tag: str) -> bool:
    """
    Send GIF via PTB bot using Telegram file_id or URL.
    Returns False silently if nothing configured.
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
    Returns False silently if nothing configured.
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


async def send_message_with_gif(
    bot,
    chat_id: str | int,
    tag: str,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
) -> object | None:
    """
    Send one combined message: GIF + caption.
    Falls back to plain text message if GIF can't be sent.
    """
    file_id = pick_gif(tag)
    if file_id:
        try:
            msg = await bot.send_animation(
                chat_id=chat_id,
                animation=file_id,
                caption=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            return msg
        except Exception as e:
            logger.warning("send_message_with_gif animation failed (tag=%s): %s", tag, e)
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
        return msg
    except Exception as e:
        logger.warning("send_message_with_gif fallback text failed (tag=%s): %s", tag, e)
        return None


def send_message_with_gif_sync(
    token: str,
    chat_id: str | int,
    tag: str,
    text: str,
    reply_markup: dict | None = None,
    parse_mode: str = "HTML",
) -> bool:
    """
    Send one combined message over raw Telegram API: GIF + caption.
    Falls back to plain text sendMessage.
    """
    file_id = pick_gif(tag)
    if file_id:
        try:
            payload = {
                "chat_id": chat_id,
                "animation": file_id,
                "caption": text,
                "parse_mode": parse_mode,
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            resp = requests.post(
                TELEGRAM_ANIMATION_API.format(token=token),
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("send_message_with_gif_sync animation failed (tag=%s): %s", tag, e)
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = requests.post(
            TELEGRAM_MESSAGE_API.format(token=token),
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("send_message_with_gif_sync fallback text failed (tag=%s): %s", tag, e)
        return False
