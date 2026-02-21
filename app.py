"""Flask app with Telegram webhook and mail checker."""
import asyncio
import logging
import random
import threading
import time
from queue import Queue

from flask import Flask, request, jsonify
from telegram import Update
from telegram.error import RetryAfter
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

import config
import db
from bot.handlers import (
    cmd_start,
    cmd_help,
    callback_create_mail,
    callback_my_mail,
    callback_refresh,
    callback_new_mail,
    callback_delete_mail,
    CB_CREATE_MAIL,
    CB_MY_MAIL,
    CB_REFRESH,
    CB_NEW_MAIL,
    CB_DELETE_MAIL,
)
from bot.sse_listener import run_mail_checker
from bot.sender import run_sender_thread

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAX_WEBHOOK_PAYLOAD = 64 * 1024  # 64 KB

# Flask app
app = Flask(__name__)

# Telegram bot application
tg_application: Application | None = None
message_queue: Queue | None = None

# Persistent event loop for PTB
_ptb_loop: asyncio.AbstractEventLoop | None = None
_ptb_loop_thread: threading.Thread | None = None


def _run_ptb_loop():
    global _ptb_loop
    _ptb_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ptb_loop)
    _ptb_loop.run_forever()


def _run_async(coro):
    future = asyncio.run_coroutine_threadsafe(coro, _ptb_loop)
    return future.result()


def build_application() -> Application:
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .build()
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CallbackQueryHandler(callback_create_mail, pattern=CB_CREATE_MAIL))
    application.add_handler(CallbackQueryHandler(callback_my_mail, pattern=CB_MY_MAIL))
    application.add_handler(CallbackQueryHandler(callback_refresh, pattern=CB_REFRESH))
    application.add_handler(CallbackQueryHandler(callback_new_mail, pattern=CB_NEW_MAIL))
    application.add_handler(CallbackQueryHandler(callback_delete_mail, pattern=CB_DELETE_MAIL))

    return application


def init_bot():
    global tg_application, message_queue, _ptb_loop_thread

    db.init_db()

    _ptb_loop_thread = threading.Thread(target=_run_ptb_loop, daemon=True)
    _ptb_loop_thread.start()
    time.sleep(0.1)

    tg_application = build_application()
    application = tg_application

    _run_async(application.initialize())

    message_queue = Queue()
    run_sender_thread(message_queue, config.TELEGRAM_BOT_TOKEN)

    def on_new_message(user_id: str, msg_id: str, parsed: dict):
        message_queue.put((user_id, parsed))

    run_mail_checker(on_new_message)

    if config.WEBHOOK_URL:
        webhook_url = f"{config.WEBHOOK_URL}/webhook"
        # Stagger set_webhook to avoid Telegram flood when multiple workers start
        time.sleep(random.uniform(0, 2))
        for attempt in range(3):
            try:
                _run_async(application.bot.set_webhook(
                    url=webhook_url,
                    secret_token=config.WEBHOOK_SECRET,
                ))
                logger.info("Webhook set: %s", webhook_url)
                break
            except RetryAfter as e:
                if attempt < 2:
                    delay = e.retry_after + 0.5
                    logger.warning("Telegram flood limit, retry in %.0fs", delay)
                    time.sleep(delay)
                else:
                    logger.exception("Webhook set failed after retries: %s", e)
                    raise
    else:
        logger.warning("WEBHOOK_URL not set - webhook mode disabled")


@app.route("/")
def index():
    return jsonify({"status": "ok", "bot": "TemperMail"})


@app.route("/webhook", methods=["POST"])
def webhook():
    if not tg_application:
        return jsonify({"ok": False}), 500

    # Validate secret token (Telegram sends it in this header)
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if token != config.WEBHOOK_SECRET:
        return jsonify({"ok": False}), 403

    # Reject oversized payloads
    if request.content_length and request.content_length > MAX_WEBHOOK_PAYLOAD:
        return jsonify({"ok": False}), 413

    # Require JSON content type
    if not request.is_json:
        return jsonify({"ok": False}), 415

    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"ok": False}), 400
        update = Update.de_json(data, tg_application.bot)
        _run_async(tg_application.process_update(update))
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Webhook error: %s", e)
        return jsonify({"ok": False}), 500


# Initialize on module load (for gunicorn/Railway)
if config.TELEGRAM_BOT_TOKEN:
    init_bot()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT)
