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
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 15))
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

# GIF style config (Telegram file_id-based)
GIF_DEFAULT_FILE_ID = os.environ.get("GIF_DEFAULT_FILE_ID", "")
GIF_DEFAULT_URL = os.environ.get(
    "GIF_DEFAULT_URL",
    "https://media.giphy.com/media/ICOgUNjpvO0PC/giphy.gif",
)
GIF_URLS = {
    "start": os.environ.get("GIF_START_URL", "https://media.giphy.com/media/ICOgUNjpvO0PC/giphy.gif"),
    "create_success": os.environ.get("GIF_CREATE_SUCCESS_URL", "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif"),
    "create_error": os.environ.get("GIF_CREATE_ERROR_URL", "https://media.giphy.com/media/3o7abB06u9bNzA8lu8/giphy.gif"),
    "refresh": os.environ.get("GIF_REFRESH_URL", "https://media.giphy.com/media/26ufdipQqU2lhNA4g/giphy.gif"),
    "no_mail": os.environ.get("GIF_NO_MAIL_URL", "https://media.giphy.com/media/3oriO0OEd9QIDdllqo/giphy.gif"),
    "new_mail": os.environ.get("GIF_NEW_MAIL_URL", "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif"),
    "expired": os.environ.get("GIF_EXPIRED_URL", "https://media.giphy.com/media/fAnEC88LccN7a/giphy.gif"),
    "rate_limited": os.environ.get("GIF_RATE_LIMITED_URL", "https://media.giphy.com/media/26xBI73gWquCBBCDe/giphy.gif"),
    "delete_success": os.environ.get("GIF_DELETE_SUCCESS_URL", "https://media.giphy.com/media/10hO3rDNqqg2Xe/giphy.gif"),
    "generic_error": os.environ.get("GIF_GENERIC_ERROR_URL", "https://media.giphy.com/media/3o7btPCcdNniyf0ArS/giphy.gif"),
    "my_mail": os.environ.get("GIF_MY_MAIL_URL", "https://media.giphy.com/media/l0HlGdXFWYbKv5rby/giphy.gif"),
}
GIF_FILE_IDS = {
    "start": os.environ.get("GIF_START_FILE_ID", ""),
    "create_success": os.environ.get("GIF_CREATE_SUCCESS_FILE_ID", ""),
    "create_error": os.environ.get("GIF_CREATE_ERROR_FILE_ID", ""),
    "refresh": os.environ.get("GIF_REFRESH_FILE_ID", ""),
    "no_mail": os.environ.get("GIF_NO_MAIL_FILE_ID", ""),
    "new_mail": os.environ.get("GIF_NEW_MAIL_FILE_ID", ""),
    "expired": os.environ.get("GIF_EXPIRED_FILE_ID", ""),
    "rate_limited": os.environ.get("GIF_RATE_LIMITED_FILE_ID", ""),
    "delete_success": os.environ.get("GIF_DELETE_SUCCESS_FILE_ID", ""),
    "generic_error": os.environ.get("GIF_GENERIC_ERROR_FILE_ID", ""),
}
