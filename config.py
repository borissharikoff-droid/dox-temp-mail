"""Configuration for the Telegram Temp Mail Bot."""
import os

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", 8080))

MAIL_TM_BASE = "https://api.mail.tm"
MAIL_TM_MERCURE = "https://mercure.mail.tm/.well-known/mercure"

# Session expiry: suggest new mail after 1 hour
SESSION_MAX_AGE_SECONDS = 3600

# Polling interval when SSE fails (seconds)
POLL_INTERVAL = 45

# Retry config for Mail.tm API
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = [1, 2, 4]  # seconds

# Max inline buttons per row (Telegram limit ~8, keep lower for readability)
MAX_LINKS_PER_MESSAGE = 5
