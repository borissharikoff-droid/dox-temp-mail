"""Mail.tm API client with retry logic."""
import random
import string
import time
import logging
from typing import Any

import requests

from config import MAIL_TM_BASE, RETRY_ATTEMPTS, RETRY_BACKOFF

logger = logging.getLogger(__name__)


def _random_string(length: int = 12) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _retry_request(method: str, url: str, **kwargs) -> requests.Response:
    """Execute request with exponential backoff on 5xx/timeout."""
    last_exc = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.request(method, url, timeout=15, **kwargs)
            if 500 <= resp.status_code < 600:
                raise requests.RequestException(f"Server error: {resp.status_code}")
            return resp
        except (requests.Timeout, requests.RequestException) as e:
            last_exc = e
            if attempt < RETRY_ATTEMPTS - 1:
                delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                logger.warning("Mail.tm request failed (attempt %d), retry in %ds: %s", attempt + 1, delay, e)
                time.sleep(delay)
    raise last_exc


def get_domains() -> list[str]:
    """Fetch available Mail.tm domains."""
    resp = _retry_request("GET", f"{MAIL_TM_BASE}/domains")
    resp.raise_for_status()
    data = resp.json()
    members = data.get("hydra:member", [])
    return [d["domain"] for d in members if d.get("isActive", True)]


def create_account() -> tuple[str, str, str]:
    """
    Create a new Mail.tm account.
    Returns (email, token, account_id).
    """
    domains = get_domains()
    if not domains:
        raise ValueError("No domains available")
    domain = random.choice(domains)
    local = _random_string(10)
    email = f"{local}@{domain}"
    password = _random_string(16)

    resp = _retry_request(
        "POST",
        f"{MAIL_TM_BASE}/accounts",
        json={"address": email, "password": password},
        headers={"Content-Type": "application/json"},
    )
    if resp.status_code == 422:
        # Address might be taken, try again with different local
        return create_account()
    resp.raise_for_status()
    account = resp.json()
    account_id = account["id"]

    resp = _retry_request(
        "POST",
        f"{MAIL_TM_BASE}/token",
        json={"address": email, "password": password},
        headers={"Content-Type": "application/json"},
    )
    resp.raise_for_status()
    token_data = resp.json()
    token = token_data["token"]

    return email, token, account_id


def get_messages(token: str) -> list[dict]:
    """Fetch message list for account."""
    resp = _retry_request(
        "GET",
        f"{MAIL_TM_BASE}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("hydra:member", [])


def get_message_detail(token: str, message_id: str) -> dict | None:
    """Fetch full message with text, html, verifications."""
    resp = _retry_request(
        "GET",
        f"{MAIL_TM_BASE}/messages/{message_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()
