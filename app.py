"""Flask app with Telegram webhook and mail checker."""
import asyncio
import logging
from queue import Queue

from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

import config
import db
from bot.handlers import (
    cmd_start,
    callback_create_mail,
    callback_my_mail,
    callback_refresh,
    callback_new_mail,
    CB_CREATE_MAIL,
    CB_MY_MAIL,
    CB_REFRESH,
    CB_NEW_MAIL,
)
from bot.sse_listener import run_mail_checker
from bot.sender import run_sender_thread

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Telegram bot application
tg_application: Application | None = None
message_queue: Queue | None = None


def build_application() -> Application:
    """Build Telegram Application with handlers."""
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .build()
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CallbackQueryHandler(callback_create_mail, pattern=CB_CREATE_MAIL))
    application.add_handler(CallbackQueryHandler(callback_my_mail, pattern=CB_MY_MAIL))
    application.add_handler(CallbackQueryHandler(callback_refresh, pattern=CB_REFRESH))
    application.add_handler(CallbackQueryHandler(callback_new_mail, pattern=CB_NEW_MAIL))

    return application


def init_bot():
    """Initialize bot, webhook, job queue, and mail checker."""
    global tg_application, message_queue

    db.init_db()

    tg_application = build_application()
    application = tg_application

    # Queue for background worker -> Telegram
    message_queue = Queue()

    # Sender thread: drain queue and send to Telegram
    run_sender_thread(message_queue, config.TELEGRAM_BOT_TOKEN)

    # Background mail checker
    def on_new_message(user_id: str, msg_id: str, parsed: dict):
        message_queue.put((user_id, parsed))

    run_mail_checker(on_new_message)

    # Set webhook
    if config.WEBHOOK_URL:
        webhook_url = f"{config.WEBHOOK_URL}/webhook"
        asyncio.run(application.bot.set_webhook(url=webhook_url))
        logger.info("Webhook set: %s", webhook_url)
    else:
        logger.warning("WEBHOOK_URL not set - webhook mode disabled")


@app.route("/")
def index():
    return jsonify({"status": "ok", "bot": "TemperMail"})


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive Telegram updates."""
    if not tg_application:
        return jsonify({"ok": False}), 500

    try:
        data = request.get_json()
        update = Update.de_json(data, tg_application.bot)
        tg_application.process_update(update)
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Webhook error: %s", e)
        return jsonify({"ok": False}), 500


# Initialize on module load (for gunicorn/Railway)
if config.TELEGRAM_BOT_TOKEN:
    init_bot()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT)
