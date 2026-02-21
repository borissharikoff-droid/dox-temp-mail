"""Telegram bot handlers."""
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import db
from config import SESSION_MAX_AGE_SECONDS
from bot.mail_service import create_account, get_messages, get_message_detail
from bot.message_parser import get_button_label, parse_message
from bot.rate_limiter import is_allowed

logger = logging.getLogger(__name__)

CB_CREATE_MAIL = "create_mail"
CB_MY_MAIL = "my_mail"
CB_REFRESH = "refresh"
CB_NEW_MAIL = "new_mail"
CB_DELETE_MAIL = "delete_mail"

HELP_TEXT = (
    "Я бот для временной почты.\n\n"
    "Кнопки:\n"
    "• *Создать почту* — получить новый временный email\n"
    "• *Моя почта* — показать текущий email и оставшееся время\n"
    "• *Обновить* — проверить входящие вручную\n"
    "• *Удалить почту* — удалить текущий email\n\n"
    "Когда придёт письмо с кодом или ссылкой — увидишь его здесь "
    "с кнопками для подтверждения.\n\n"
    "Почта живёт ~1 час. Потом лучше создать новую."
)


# ── Keyboards ──────────────────────────────────────────────────────

def _kb_no_mail() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Создать почту", callback_data=CB_CREATE_MAIL)],
    ])


def _kb_active() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Моя почта", callback_data=CB_MY_MAIL),
            InlineKeyboardButton("Обновить", callback_data=CB_REFRESH),
        ],
        [InlineKeyboardButton("Удалить почту", callback_data=CB_DELETE_MAIL)],
    ])


def _kb_expired() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Создать новую почту", callback_data=CB_NEW_MAIL)],
    ])


# ── Helpers ────────────────────────────────────────────────────────

def _parse_created_at(created_at: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _is_session_expired(created_at: str) -> bool:
    dt = _parse_created_at(created_at)
    if dt is None:
        return True
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    return age > SESSION_MAX_AGE_SECONDS


def _remaining_ttl(created_at: str) -> str:
    dt = _parse_created_at(created_at)
    if dt is None:
        return "неизвестно"
    remaining = SESSION_MAX_AGE_SECONDS - (datetime.now(timezone.utc) - dt).total_seconds()
    if remaining <= 0:
        return "истекло"
    mins = int(remaining // 60)
    return f"{mins} мин"


def _keyboard_for_user(user_id: str) -> InlineKeyboardMarkup:
    session = db.get_session(user_id)
    if not session:
        return _kb_no_mail()
    if _is_session_expired(session["created_at"]):
        return _kb_expired()
    return _kb_active()


async def _rate_check(update: Update, action: str) -> bool:
    """Return True if request is throttled (caller should return early)."""
    user_id = str(update.effective_user.id)
    if is_allowed(user_id, action):
        return False
    if update.callback_query:
        await update.callback_query.answer(
            "Слишком много запросов. Подожди немного.",
            show_alert=True,
        )
    return True


# ── Command handlers ───────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _rate_check(update, "general"):
        return
    user_id = str(update.effective_user.id)
    await update.message.reply_text(
        f"Привет!\n\n{HELP_TEXT}",
        reply_markup=_keyboard_for_user(user_id),
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _rate_check(update, "general"):
        return
    user_id = str(update.effective_user.id)
    await update.message.reply_text(
        HELP_TEXT,
        reply_markup=_keyboard_for_user(user_id),
        parse_mode="Markdown",
    )


# ── Callback handlers ─────────────────────────────────────────────

async def callback_create_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await _rate_check(update, "create_mail"):
        return
    user_id = str(update.effective_user.id)

    await query.edit_message_text("Создаю почту...")

    try:
        email, token, account_id = create_account()
        db.save_session(user_id, email, token, account_id)
        await query.edit_message_text(
            f"Ваша почта:\n`{email}`\n\n"
            "Скопируй и используй для регистрации. "
            "Письма будут приходить сюда.",
            reply_markup=_kb_active(),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("create_account failed: %s", e)
        await query.edit_message_text(
            "Ошибка при создании почты. Попробуй позже.",
            reply_markup=_kb_no_mail(),
        )


async def callback_my_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await _rate_check(update, "general"):
        return
    user_id = str(update.effective_user.id)

    session = db.get_session(user_id)
    if not session:
        await query.edit_message_text(
            "У тебя пока нет почты. Нажми «Создать почту».",
            reply_markup=_kb_no_mail(),
        )
        return

    if _is_session_expired(session["created_at"]):
        await query.edit_message_text(
            "Почта устарела (прошло больше часа). Создать новую?",
            reply_markup=_kb_expired(),
        )
        return

    ttl = _remaining_ttl(session["created_at"])
    await query.edit_message_text(
        f"Твоя почта:\n`{session['email']}`\n\nОсталось: {ttl}",
        reply_markup=_kb_active(),
        parse_mode="Markdown",
    )


async def callback_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await _rate_check(update, "refresh"):
        return
    user_id = str(update.effective_user.id)

    session = db.get_session(user_id)
    if not session:
        await query.edit_message_text(
            "Сначала создай почту.",
            reply_markup=_kb_no_mail(),
        )
        return

    if _is_session_expired(session["created_at"]):
        await query.edit_message_text(
            "Почта устарела. Создать новую?",
            reply_markup=_kb_expired(),
        )
        return

    await query.edit_message_text("Проверяю почту...")

    try:
        messages = get_messages(session["token"])
        new_count = 0
        for msg in messages:
            msg_id = msg.get("id")
            if msg_id and not db.is_message_seen(msg_id):
                detail = get_message_detail(session["token"], msg_id)
                parsed = parse_message(msg, detail)
                await _send_message_to_user(context, user_id, parsed)
                db.mark_message_seen(msg_id)
                new_count += 1

        if new_count == 0:
            await query.edit_message_text(
                "Новых писем нет.",
                reply_markup=_kb_active(),
            )
        else:
            await query.edit_message_text(
                f"Найдено новых писем: {new_count}.",
                reply_markup=_kb_active(),
            )
    except Exception as e:
        logger.exception("refresh failed: %s", e)
        await query.edit_message_text(
            "Ошибка при проверке почты. Попробуй позже.",
            reply_markup=_kb_active(),
        )


async def callback_new_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await callback_create_mail(update, context)


async def callback_delete_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await _rate_check(update, "general"):
        return
    user_id = str(update.effective_user.id)

    session = db.get_session(user_id)
    if not session:
        await query.edit_message_text(
            "Почты нет — удалять нечего.",
            reply_markup=_kb_no_mail(),
        )
        return

    db.delete_session(user_id)
    await query.edit_message_text(
        "Почта удалена. Можешь создать новую.",
        reply_markup=_kb_no_mail(),
    )


# ── Email rendering ───────────────────────────────────────────────

async def _send_message_to_user(context: ContextTypes.DEFAULT_TYPE, user_id: str, parsed: dict):
    lines = [
        f"📧 *От:* {parsed['from_addr']}",
        f"*Тема:* {parsed['subject']}",
        "",
    ]
    if parsed.get("intro"):
        lines.append(parsed["intro"][:400])
        if len(parsed.get("intro", "")) > 400:
            lines.append("...")

    if parsed.get("codes"):
        lines.append("")
        lines.append("*Коды:* " + ", ".join(f"`{c}`" for c in parsed["codes"]))

    text = "\n".join(lines)

    buttons = []
    url_labels = parsed.get("url_labels") or {}
    for url in parsed.get("urls", [])[:5]:
        label = get_button_label(url, url_labels.get(url))
        buttons.append([InlineKeyboardButton(label, url=url)])

    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

    await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
