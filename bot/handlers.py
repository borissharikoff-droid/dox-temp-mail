"""Telegram bot handlers."""
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import db
from config import SESSION_MAX_AGE_SECONDS
from bot.mail_service import create_account, get_messages, get_message_detail
from bot.media_style import send_gif
from bot.message_parser import get_button_label, parse_message
from bot.rate_limiter import is_allowed

logger = logging.getLogger(__name__)

CB_CREATE_MAIL = "create_mail"
CB_MY_MAIL = "my_mail"
CB_REFRESH = "refresh"
CB_NEW_MAIL = "new_mail"
CB_DELETE_MAIL = "delete_mail"

HELP_TEXT = (
    "Йо! Это твой временный почтовый напарник 😎\n\n"
    "Что умеем:\n"
    "• *📬 Сварганить почту* — сделать временный ящик\n"
    "• *📫 Мой ящик* — показать текущий адрес и сколько он еще живет\n"
    "• *🔄 Чекнуть* — быстро глянуть входящие\n"
    "• *🗑 Снести ящик* — удалить текущую почту\n\n"
    "Если честно, впадлу светить основную почту везде подряд — "
    "поэтому тут и крутим временный ящик.\n"
    "Живет он около часа, потом лучше сделать новый."
)


def _kb_no_mail() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📬 Сварганить почту", callback_data=CB_CREATE_MAIL)],
    ])


def _kb_active() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📫 Мой ящик", callback_data=CB_MY_MAIL),
            InlineKeyboardButton("🔄 Чекнуть", callback_data=CB_REFRESH),
        ],
        [InlineKeyboardButton("🗑 Снести ящик", callback_data=CB_DELETE_MAIL)],
    ])


def _kb_expired() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♻️ Новый ящик", callback_data=CB_NEW_MAIL)],
    ])


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
        return "непонятно сколько"
    remaining = SESSION_MAX_AGE_SECONDS - (datetime.now(timezone.utc) - dt).total_seconds()
    if remaining <= 0:
        return "время вышло"
    mins = int(remaining // 60)
    return f"{mins} мин"


def _keyboard_for_user(user_id: str) -> InlineKeyboardMarkup:
    session = db.get_session(user_id)
    if not session:
        return _kb_no_mail()
    if _is_session_expired(session["created_at"]):
        return _kb_expired()
    return _kb_active()


async def _rate_check(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> bool:
    """Return True if request is throttled (caller should return early)."""
    user_id = str(update.effective_user.id)
    if is_allowed(user_id, action):
        return False

    await send_gif(context.bot, update.effective_chat.id, "rate_limited")
    if update.callback_query:
        await update.callback_query.answer(
            "Полегче, ковбой 🤠 Слишком много запросов, дай 10 сек передышки.",
            show_alert=True,
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Слишком быстро жмешь. Чуть притормози и снова в бой.",
        )
    return True


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _rate_check(update, context, "general"):
        return
    user_id = str(update.effective_user.id)
    await send_gif(context.bot, user_id, "start")
    await update.message.reply_text(
        f"Здарова!\n\n{HELP_TEXT}",
        reply_markup=_keyboard_for_user(user_id),
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _rate_check(update, context, "general"):
        return
    user_id = str(update.effective_user.id)
    await send_gif(context.bot, user_id, "start")
    await update.message.reply_text(
        HELP_TEXT,
        reply_markup=_keyboard_for_user(user_id),
        parse_mode="Markdown",
    )


async def callback_create_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await _rate_check(update, context, "create_mail"):
        return
    user_id = str(update.effective_user.id)

    await send_gif(context.bot, user_id, "refresh")
    await query.edit_message_text("Варю ящик... секунду 👨‍🍳")

    try:
        email, token, account_id = create_account()
        db.save_session(user_id, email, token, account_id)
        await send_gif(context.bot, user_id, "create_success")
        await query.edit_message_text(
            f"Готово, держи:\n`{email}`\n\n"
            "Юзай его для регистраций, а основную почту побережем 😏",
            reply_markup=_kb_active(),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("create_account failed: %s", e)
        await send_gif(context.bot, user_id, "create_error")
        await query.edit_message_text(
            "Упс, ящик сейчас не сварился. Повтори чуть позже.",
            reply_markup=_kb_no_mail(),
        )


async def callback_my_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await _rate_check(update, context, "general"):
        return
    user_id = str(update.effective_user.id)

    session = db.get_session(user_id)
    if not session:
        await send_gif(context.bot, user_id, "no_mail")
        await query.edit_message_text(
            "Пока пусто. Жми *📬 Сварганить почту* и погнали.",
            reply_markup=_kb_no_mail(),
            parse_mode="Markdown",
        )
        return

    if _is_session_expired(session["created_at"]):
        await send_gif(context.bot, user_id, "expired")
        await query.edit_message_text(
            "Этот ящик уже выдохся. Делаем новый?",
            reply_markup=_kb_expired(),
        )
        return

    ttl = _remaining_ttl(session["created_at"])
    await send_gif(context.bot, user_id, "start")
    await query.edit_message_text(
        f"Твой ящик:\n`{session['email']}`\n\nОсталось жить: {ttl}",
        reply_markup=_kb_active(),
        parse_mode="Markdown",
    )


async def callback_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await _rate_check(update, context, "refresh"):
        return
    user_id = str(update.effective_user.id)

    session = db.get_session(user_id)
    if not session:
        await send_gif(context.bot, user_id, "no_mail")
        await query.edit_message_text(
            "Сначала нужен ящик. Жми *📬 Сварганить почту*.",
            reply_markup=_kb_no_mail(),
            parse_mode="Markdown",
        )
        return

    if _is_session_expired(session["created_at"]):
        await send_gif(context.bot, user_id, "expired")
        await query.edit_message_text(
            "Ящик устарел. Переобуваемся в новый?",
            reply_markup=_kb_expired(),
        )
        return

    await send_gif(context.bot, user_id, "refresh")
    await query.edit_message_text("Ща чекну входящие, не переключайся 👀")

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
            await send_gif(context.bot, user_id, "no_mail")
            await query.edit_message_text(
                "Пока тишина. Новых писем нет.",
                reply_markup=_kb_active(),
            )
        else:
            await send_gif(context.bot, user_id, "new_mail")
            await query.edit_message_text(
                f"Залетело писем: {new_count}. Красиво.",
                reply_markup=_kb_active(),
            )
    except Exception as e:
        logger.exception("refresh failed: %s", e)
        await send_gif(context.bot, user_id, "generic_error")
        await query.edit_message_text(
            "Сервак чутка закашлялся. Давай еще разок позже.",
            reply_markup=_kb_active(),
        )


async def callback_new_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await callback_create_mail(update, context)


async def callback_delete_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await _rate_check(update, context, "general"):
        return
    user_id = str(update.effective_user.id)

    session = db.get_session(user_id)
    if not session:
        await send_gif(context.bot, user_id, "no_mail")
        await query.edit_message_text(
            "Нечего сносить, ящик уже пустой.",
            reply_markup=_kb_no_mail(),
        )
        return

    db.delete_session(user_id)
    await send_gif(context.bot, user_id, "delete_success")
    await query.edit_message_text(
        "Готово, ящик снесен. Если надо — сделаем новый за секунду.",
        reply_markup=_kb_no_mail(),
    )


async def _send_message_to_user(context: ContextTypes.DEFAULT_TYPE, user_id: str, parsed: dict):
    await send_gif(context.bot, user_id, "new_mail")

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
