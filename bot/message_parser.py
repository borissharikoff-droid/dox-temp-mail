"""Extract links, codes, and verifications from email content."""
import re
from typing import Any

from config import MAX_LINKS_PER_MESSAGE

# URL regex - matches http/https links
URL_PATTERN = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)

# HTML href attribute
HREF_PATTERN = re.compile(r'href=["\']?(https?://[^"\'>\s]+)["\']?', re.IGNORECASE)

# Verification codes: 4-8 chars, often digits or alphanumeric
CODE_PATTERNS = [
    re.compile(r"\b(\d{6})\b"),  # 6 digits
    re.compile(r"\b(\d{4})\b"),  # 4 digits
    re.compile(r"\b(\d{8})\b"),  # 8 digits
    re.compile(r"\b([A-Za-z0-9]{4,8})\b"),  # 4-8 alphanumeric
    re.compile(r"code[:\s]+([A-Za-z0-9]{4,8})", re.IGNORECASE),
    re.compile(r"verification[:\s]+([A-Za-z0-9]{4,8})", re.IGNORECASE),
    re.compile(r"otp[:\s]+([A-Za-z0-9]{4,8})", re.IGNORECASE),
]


def extract_urls(text: str | None, html: list[str] | None) -> list[str]:
    """Extract unique URLs from text and HTML."""
    urls = set()
    if text:
        urls.update(URL_PATTERN.findall(text))
        urls.update(HREF_PATTERN.findall(text))
    if html:
        for block in html:
            if isinstance(block, str):
                urls.update(URL_PATTERN.findall(block))
                urls.update(HREF_PATTERN.findall(block))
    # Deduplicate, preserve order, limit length
    seen = set()
    result = []
    for u in urls:
        u_clean = u.rstrip(".,;:!")
        if u_clean not in seen and len(u_clean) < 500:
            seen.add(u_clean)
            result.append(u_clean)
    return result[:MAX_LINKS_PER_MESSAGE]


def extract_codes(text: str | None) -> list[str]:
    """Extract verification/code-like strings from text."""
    if not text:
        return []
    codes = set()
    for pat in CODE_PATTERNS:
        for m in pat.finditer(text):
            code = m.group(1)
            if code and len(code) >= 4 and len(code) <= 8:
                codes.add(code)
    return list(codes)[:10]


def parse_message(message: dict, detail: dict | None = None) -> dict[str, Any]:
    """
    Parse message and detail into structured data for Telegram.
    Returns: {
        "subject": str,
        "from_addr": str,
        "intro": str,
        "codes": list[str],
        "urls": list[str],
        "verifications": list[str],
    }
    """
    subject = message.get("subject", "") or "(без темы)"
    from_obj = message.get("from") or {}
    from_addr = from_obj.get("address", "") if isinstance(from_obj, dict) else str(from_obj)
    intro = message.get("intro", "") or ""

    text = ""
    html = []
    verifications = []

    if detail:
        text = detail.get("text") or ""
        html = detail.get("html") or []
        verifications = detail.get("verifications") or []
        if isinstance(verifications, str):
            verifications = [verifications] if verifications else []

    urls = extract_urls(text or intro, html if html else [intro])
    codes = extract_codes(text or intro)

    # Add verification URLs
    for v in verifications:
        if v and v.startswith("http") and v not in urls:
            urls.insert(0, v)
    urls = urls[:MAX_LINKS_PER_MESSAGE]

    return {
        "subject": subject,
        "from_addr": from_addr,
        "intro": intro[:500] if intro else "",
        "codes": codes,
        "urls": urls,
        "verifications": verifications,
    }
