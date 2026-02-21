"""Configuration for the Telegram Temp Mail Bot."""
import os
import uuid

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "") or uuid.uuid4().hex
PORT = int(os.environ.get("PORT", 8080))

MAIL_TM_BASE = "https://api.mail.tm"
MAIL_TM_MERCURE = "https://mercure.mail.tm/.well-known/mercure"

# Session expiry: suggest new mail after 1 hour
SESSION_MAX_AGE_SECONDS = 3600

# Polling
POLL_INTERVAL = 45
MAX_CONCURRENT_POLLS = 10

# Retry config for Mail.tm API
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = [1, 2, 4]  # seconds

# Max inline buttons per row (Telegram limit ~8, keep lower for readability)
MAX_LINKS_PER_MESSAGE = 5

# Rate limits (per user)
RATE_LIMIT_CREATE = 3        # max email creations per hour
RATE_LIMIT_REFRESH = 10      # max refreshes per minute
RATE_LIMIT_GENERAL = 20      # max other actions per minute
