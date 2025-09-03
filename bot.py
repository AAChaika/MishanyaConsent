import os, asyncio
from datetime import timedelta
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatPermissions,
)
from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CONSENT_VERSION = os.getenv("CONSENT_VERSION", "1.0")
POLICY_URL = os.getenv("POLICY_URL", "https://example.com/privacy")
KICK_AFTER_SECONDS = int(os.getenv("KICK_AFTER_SECONDS", "300"))  # 5 minutes

if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN env var")

CONSENT_TEXT = (
    "👋 Добро пожаловать в группу Mishanya, {name}!\n\n"
    "Чтобы продолжить, просьба дать **согласие на обработку персональных данных**. "
    "Мы **не храним** ваши персональные данные.\n\n"
    f"📄 Политика Конфиденциальности: {POLICY_URL}\n\n"
)
# In-memory pending map: key=(chat_id, user_id) -> {task, msg_id}
PENDING: dict[tuple[int, int], dict] = {}

MUTED = ChatPermissions(  # can read only
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
)

UNMUTED = ChatPermissions(  # default: allow sending messages
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)

async def _schedule_kick(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, msg_id: int):
    """Kick user after timeout if still pending."""
    try:
        await asyncio.sleep(KICK_AFTER_SECONDS)
        key = (chat_id, user_id)
        if key in PENDING:
            # still pending → kick
            await context.bot.ban_chat_member(chat_id, user_id, until_date=timedelta(seconds=60))  # short ban
            # cleanup consent message if still there
            try:
                await context.bot.delete_message(chat_id, msg_id)
            except Exception:
                pass
            PENDING.pop(key, None)
            # Optional: post a short note (auto-delete)
            try:
                m = await context.bot.send_message(chat_id, f"⏰ <a href='tg://user?id={user_id}'>User</a> did not accept in time and was removed.", parse_mode="HTML")
                await asyncio.sleep(5)
                await context.bot.delete_message(chat_id, m.message_id)
            except Exception:
                pass
    except Exception:
        pass

async def on_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    if not msg.new_chat_members:
        return

    for user in msg.new_chat_members:
        # Immediately mute the new member
        try:
            await context.bot.restrict_chat_member(chat.id, user.id, permissions=MUTED)
        except Exception:
            # Bot must be admin with "Restrict members" permission
            continue

        # Post consent message in-group, addressed to the user
        text = CONSENT_TEXT.format(name=(user.first_name or "there"))
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ I accept", callback_data=f"accept:{chat.id}:{user.id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"decline:{chat.id}:{user.id}"),
        ]])
        try:
            m = await context.bot.send_message(chat.id, text, reply_markup=keyboard, disable_web_page_preview=True)
        except Exception:
            continue

        # Remember pending + start timeout task
        key = (chat.id, user.id)
        # Cancel any previous (shouldn't happen, but safe)
        if key in PENDING and PENDING[key].get("task"):
            PENDING[key]["task"].cancel()
        task = asyncio.create_task(_schedule_kick(context, chat.id, user.id, m.message_id))
        PENDING[key] = {"task": task, "msg_id": m.message_id}

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        action, chat_id, user_id = q.data.split(":")
        chat_id = int(chat_id); user_id = int(user_id)
    except Exception:
        return

    key = (chat_id, user_id)
    actor_id = q.from_user.id

    # Only allow the targeted user or an admin to press the buttons
    if actor_id != user_id:
        # show a tiny alert and ignore
        await q.answer("This button isn’t for you.", show_alert=True)
        return

    # Clean consent message
    try:
        await context.bot.delete_message(chat_id, PENDING.get(key, {}).get("msg_id", q.message.message_id))
    except Exception:
        pass

    if action == "accept":
        # Unmute user
        try:
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=UNMUTED)
        except Exception:
            pass
        await q.edit_message_text("✅ You’re all set — welcome!", disable_web_page_preview=True)
        await asyncio.sleep(3)
        try:
            await context.bot.delete_message(q.message.chat_id, q.message.message_id)
        except Exception:
            pass
    else:
    try:
        # Kick user once
        await context.bot.ban_chat_member(chat_id, user_id)
        # Immediately unban so they can rejoin right away
        await context.bot.unban_chat_member(chat_id, user_id)
    except Exception:
        pass

    # Send a short confirmation instead of editing the deleted message
    m = await context.bot.send_message(
        chat_id,
        f"❌ <a href='tg://user?id={user_id}'>Пользователь</a> отказался и был удалён. "
        "Он может вернуться, если передумает.",
        parse_mode="HTML"
    )
    # Auto-delete after 5 seconds to keep the group clean
    await asyncio.sleep(5)
    try:
        await context.bot.delete_message(chat_id, m.message_id)
    except Exception:
        pass

    # Cancel pending timeout
    if key in PENDING and PENDING[key].get("task"):
        PENDING[key]["task"].cancel()
    PENDING.pop(key, None)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("I work automatically when new members join. Make me an admin with 'Delete messages' and 'Restrict members'.")

def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(CommandHandler("start", start_cmd))
    return app

if __name__ == "__main__":
    app = build_app()
    print("Bot running… (group consent, 5-min kick, no logs)")
    app.run_polling(allowed_updates=["message", "callback_query"])
