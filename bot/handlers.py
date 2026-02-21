"""Telegram bot handlers."""
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import db
from config import SESSION_MAX_AGE_SECONDS
from bot.mail_service import create_account, get_messages, get_message_detail
from bot.message_parser import get_button_label, parse_message

logger = logging.getLogger(__name__)

# Button callback data
CB_CREATE_MAIL = "create_mail"
CB_MY_MAIL = "my_mail"
CB_REFRESH = "refresh"
CB_NEW_MAIL = "new_mail"


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Создать почту", callback_data=CB_CREATE_MAIL),
            InlineKeyboardButton("Моя почта", callback_data=CB_MY_MAIL),
        ],
        [InlineKeyboardButton("Обновить", callback_data=CB_REFRESH)],
    ])


def _is_session_expired(created_at: str) -> bool:
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age > SESSION_MAX_AGE_SECONDS
    except Exception:
        return True


def _expired_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Создать новую почту", callback_data=CB_NEW_MAIL)],
    ])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    text = (
        "Привет! Я бот для временной почты.\n\n"
        "Используй кнопки ниже:\n"
        "• **Создать почту** — получить новый временный email\n"
        "• **Моя почта** — показать текущий email\n"
        "• **Обновить** — проверить входящие вручную\n\n"
        "Когда придёт письмо с кодом или ссылкой — увидишь его здесь с кнопками для подтверждения.\n\n"
        "Почта живёт ~1 час. Потом лучше создать новую."
    )
    await update.message.reply_text(
        text,
        reply_markup=_main_keyboard(),
        parse_mode="Markdown",
    )


async def callback_create_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create new temp mail."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)

    await query.edit_message_text("Создаю почту...")

    try:
        email, token, account_id = create_account()
        db.save_session(user_id, email, token, account_id)
        await query.edit_message_text(
            f"Ваша почта:\n`{email}`\n\nСкопируй и используй для регистрации. "
            "Письма будут приходить сюда.",
            reply_markup=_main_keyboard(),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("create_account failed: %s", e)
        await query.edit_message_text(
            f"Ошибка при создании почты. Попробуй позже.\n\n{str(e)}",
            reply_markup=_main_keyboard(),
        )


async def callback_my_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current mail or prompt to create."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)

    session = db.get_session(user_id)
    if not session:
        await query.edit_message_text(
            "У тебя пока нет почты. Нажми «Создать почту».",
            reply_markup=_main_keyboard(),
        )
        return

    if _is_session_expired(session["created_at"]):
        await query.edit_message_text(
            "Почта устарела (прошло больше часа). Создать новую?",
            reply_markup=_expired_keyboard(),
        )
        return

    await query.edit_message_text(
        f"Твоя почта:\n`{session['email']}`",
        reply_markup=_main_keyboard(),
        parse_mode="Markdown",
    )


async def callback_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually check for new messages."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)

    session = db.get_session(user_id)
    if not session:
        await query.edit_message_text(
            "Сначала создай почту.",
            reply_markup=_main_keyboard(),
        )
        return

    if _is_session_expired(session["created_at"]):
        await query.edit_message_text(
            "Почта устарела. Создать новую?",
            reply_markup=_expired_keyboard(),
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
                reply_markup=_main_keyboard(),
            )
        else:
            await query.edit_message_text(
                f"Проверено. Найдено новых писем: {new_count}.",
                reply_markup=_main_keyboard(),
            )
    except Exception as e:
        logger.exception("refresh failed: %s", e)
        await query.edit_message_text(
            f"Ошибка при проверке: {e}",
            reply_markup=_main_keyboard(),
        )


async def callback_new_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create new mail when old one expired."""
    await callback_create_mail(update, context)


async def _send_message_to_user(context: ContextTypes.DEFAULT_TYPE, user_id: str, parsed: dict):
    """Format and send parsed email to user with inline buttons."""
    lines = [
        f"📧 **От:** {parsed['from_addr']}",
        f"**Тема:** {parsed['subject']}",
        "",
    ]
    if parsed.get("intro"):
        lines.append(parsed["intro"][:400])
        if len(parsed.get("intro", "")) > 400:
            lines.append("...")

    if parsed.get("codes"):
        lines.append("")
        lines.append("**Коды:** " + ", ".join(parsed["codes"]))

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


