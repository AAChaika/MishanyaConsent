import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    ChatJoinRequestHandler,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# ----- ENV VARS -----
BOT_TOKEN = os.getenv("BOT_TOKEN")                # from @BotFather, no quotes/spaces
CHANNEL_ID = os.getenv("CHANNEL_ID")              # e.g. -1001234567890 or @YourChannel
CONSENT_VERSION = os.getenv("CONSENT_VERSION", "1.0")
POLICY_URL = os.getenv("POLICY_URL", "https://example.com/privacy")

# Basic safety checks
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN env var")

CONSENT_MESSAGE = (
    "To join this channel, please confirm your consent to the processing of your personal data.\n\n"
    "We only process what Telegram provides during this action (your account identity) to decide on access.\n"
    "We do NOT store any logs of your decision.\n\n"
    f"📄 Privacy Policy: {POLICY_URL}\n\n"
    f"By pressing ✅ I Consent, you agree to this (v{CONSENT_VERSION})."
)

# ----- HANDLERS -----
async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I Consent", callback_data=f"consent:yes:{req.user_chat_id}:{req.from_user.id}"),
         InlineKeyboardButton("❌ No",        callback_data=f"consent:no:{req.user_chat_id}:{req.from_user.id}")]
    ])
    try:
        await context.bot.send_message(
            chat_id=req.user_chat_id,
            text=CONSENT_MESSAGE,
            reply_markup=keyboard,
        )
    except Exception:
        # If DM fails for any reason, leave the request pending for a human admin
        pass

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        tag, choice, user_chat_id, from_user_id = query.data.split(":")
    except Exception:
        return
    if tag != "consent":
        return

    from_user_id = int(from_user_id)

    if choice == "yes":
        await context.bot.approve_chat_join_request(chat_id=CHANNEL_ID, user_id=from_user_id)
        await query.edit_message_text("Thanks! Your request has been approved. Welcome 👋")
    else:
        await context.bot.decline_chat_join_request(chat_id=CHANNEL_ID, user_id=from_user_id)
        await query.edit_message_text("Understood. Your request was declined.")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Optional manual start (for pinned post / deep-link like t.me/YourBot?start=consent)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I Consent", callback_data=f"consent:yes:{update.effective_chat.id}:{update.effective_user.id}"),
         InlineKeyboardButton("❌ No",        callback_data=f"consent:no:{update.effective_chat.id}:{update.effective_user.id}")]
    ])
    await update.message.reply_text(CONSENT_MESSAGE, reply_markup=keyboard)

# ----- APP BOOTSTRAP (PTB v22.x) -----
def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(ChatJoinRequestHandler(on_join_request))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(CommandHandler("start", start_cmd))
    return app

if __name__ == "__main__":
    app = build_app()
    print("Bot running… (no logs mode)")
    # Blocks and keeps the bot alive; no manual initialize/start/idle needed
    app.run_polling(allowed_updates=["chat_join_request", "callback_query", "message"])
