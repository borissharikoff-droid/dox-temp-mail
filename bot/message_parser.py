"""Extract links, codes, and verifications from email content."""
import re
from typing import Any

from config import MAX_LINKS_PER_MESSAGE

# URL regex - matches http/https links
URL_PATTERN = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)

# HTML href attribute
HREF_PATTERN = re.compile(r'href=["\']?(https?://[^"\'>\s]+)["\']?', re.IGNORECASE)

# <a href="url">link text</a> - extract url and button text
HREF_WITH_TEXT = re.compile(
    r'<a[^>]*href=["\']?(https?://[^"\'>\s]+)["\']?[^>]*>([^<]{1,40})</a>',
    re.IGNORECASE | re.DOTALL,
)

# Verification codes: digits or explicit code/verify/otp patterns (avoid matching common words)
CODE_PATTERNS = [
    re.compile(r"\b(\d{6})\b"),  # 6 digits
    re.compile(r"\b(\d{4})\b"),  # 4 digits
    re.compile(r"\b(\d{8})\b"),  # 8 digits
    re.compile(r"code[:\s]+([A-Za-z0-9]{4,12})", re.IGNORECASE),
    re.compile(r"verification[:\s]+([A-Za-z0-9]{4,12})", re.IGNORECASE),
    re.compile(r"otp[:\s]+([A-Za-z0-9]{4,12})", re.IGNORECASE),
    re.compile(r"activate[:\s]+([A-Za-z0-9]{4,12})", re.IGNORECASE),
    re.compile(r"([A-Za-z0-9]{6,12})\s*(?:is your|код|code)", re.IGNORECASE),
]

# Common words to exclude from "codes" (false positives)
CODE_STOPLIST = frozenset({
    "team", "logo", "started", "paste", "below", "message", "reserved", "medium",
    "quadcode",  # QuadCode branding - false positive
    "click", "here", "link", "view", "open", "read", "more", "less", "some",
    "your", "this", "that", "with", "from", "have", "been", "will", "would",
    "could", "should", "about", "into", "only", "over", "such", "than",
    "them", "they", "when", "where", "which", "while", "after", "before",
    "right", "left", "back", "next", "then", "just", "also", "very",
    "html", "body", "head", "span", "div", "font", "size", "color",
    "width", "height", "style", "class", "href", "http", "https",
})


def _is_image_or_tracking(url: str) -> bool:
    """Exclude image URLs and tracking pixels."""
    u = url.lower()
    if any(u.endswith(ext) or ext in u.split("?")[0] for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico")):
        return True
    if any(x in u for x in ("/pixel", "tracking", "analytics", "pixel.", "unsubscribe", "open?",
                            "cdn.", "static.", "img.", "images.", "assets.", "logo.", "icon.")):
        return True
    return False


def _activation_priority(url: str) -> int:
    """Lower = higher priority. Activation/verify links first."""
    u = url.lower()
    if any(x in u for x in ("activate", "activation", "verify", "verification", "confirm", "confirmation")):
        return 0
    if any(x in u for x in ("signup", "sign-up", "register", "token", "auth")):
        return 1
    return 2


def get_button_label(url: str, link_text: str | None = None) -> str:
    """Return human-readable label for URL button. Uses link_text from HTML if valid."""
    if link_text:
        clean = re.sub(r"\s+", " ", link_text).strip()
        if clean and len(clean) <= 35 and not clean.startswith("http"):
            return clean
    u = url.lower()
    if "activate" in u or "activation" in u:
        return "✅ Активировать"
    if "verify" in u or "verification" in u:
        return "✅ Подтвердить"
    if "confirm" in u or "confirmation" in u:
        return "✅ Подтвердить"
    if "signup" in u or "sign-up" in u or "register" in u:
        return "📝 Регистрация"
    if "welcome" in u or "signin" in u or "login" in u:
        return "🔐 Войти"
    if len(url) <= 40:
        return url
    return "Открыть ссылку"


def _extract_url_labels(html: list[str] | None) -> dict[str, str]:
    """Extract url -> link text from HTML <a> tags."""
    labels = {}
    if not html:
        return labels
    for block in html:
        if not isinstance(block, str):
            continue
        for m in HREF_WITH_TEXT.finditer(block):
            url = m.group(1).rstrip(".,;:!)")
            text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if url and text and url not in labels:
                labels[url] = text[:35]
    return labels


def extract_urls(text: str | None, html: list[str] | None) -> list[str]:
    """Extract unique URLs from text and HTML. Excludes images/tracking, prioritizes activation links."""
    urls = set()
    if text:
        urls.update(URL_PATTERN.findall(text))
        urls.update(HREF_PATTERN.findall(text))
    if html:
        for block in html:
            if isinstance(block, str):
                urls.update(URL_PATTERN.findall(block))
                urls.update(HREF_PATTERN.findall(block))
    # Deduplicate, filter junk, prioritize activation links
    seen = set()
    candidates = []
    for u in urls:
        u_clean = u.rstrip(".,;:!)")
        if u_clean not in seen and len(u_clean) < 500 and not _is_image_or_tracking(u_clean):
            seen.add(u_clean)
            candidates.append(u_clean)
    candidates.sort(key=_activation_priority)
    return candidates[:MAX_LINKS_PER_MESSAGE]


def extract_codes(text: str | None) -> list[str]:
    """Extract verification/code-like strings from text. Excludes common words."""
    if not text:
        return []
    codes = set()
    for pat in CODE_PATTERNS:
        for m in pat.finditer(text):
            code = m.group(1)
            if code and 4 <= len(code) <= 12 and code.lower() not in CODE_STOPLIST:
                # Prefer codes with digits or mixed case (less likely to be words)
                has_digit = any(c.isdigit() for c in code)
                if has_digit or len(code) >= 7:
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
    url_labels = _extract_url_labels(html if html else [intro] if intro else None)

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
        "url_labels": url_labels,
        "verifications": verifications,
    }
