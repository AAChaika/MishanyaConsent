import asyncio, os, datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, ChatJoinRequestHandler, CallbackQueryHandler, CommandHandler, ContextTypes

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # e.g. -100123..., or '@yourchannel'
CONSENT_VERSION = os.getenv("CONSENT_VERSION", "1.0")
POLICY_URL = os.getenv("POLICY_URL", "https://example.com/privacy")

CONSENT_MESSAGE = (
    "To join this channel, please confirm your consent to the processing of your personal data.\n\n"
    "We only process what Telegram naturally provides during this action (your account identity) to decide on access.\n"
    "We do NOT store any logs of your decision.\n\n"
    f"📄 Privacy Policy: {POLICY_URL}\n\n"
    f"By pressing ✅ I Consent, you agree to this (v{CONSENT_VERSION})."
)

async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    # Show inline consent in user’s DM
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I Consent", callback_data=f"consent:yes:{req.user_chat_id}:{req.from_user.id}"),
         InlineKeyboardButton("❌ No",        callback_data=f"consent:no:{req.user_chat_id}:{req.from_user.id}")]
    ])
    try:
        await context.bot.send_message(chat_id=req.user_chat_id, text=CONSENT_MESSAGE, reply_markup=keyboard)
    except Exception:
        # If DM fails, leave the request pending for a human admin
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
        # Approve without storing any data
        await context.bot.approve_chat_join_request(chat_id=CHANNEL_ID, user_id=from_user_id)
        await query.edit_message_text("Thanks! Your request has been approved. Welcome 👋")
    else:
        await context.bot.decline_chat_join_request(chat_id=CHANNEL_ID, user_id=from_user_id)
        await query.edit_message_text("Understood. Your request was declined.")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Optional: manual start path (useful for pinned posts/deep-links)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I Consent", callback_data=f"consent:yes:{update.effective_chat.id}:{update.effective_user.id}"),
         InlineKeyboardButton("❌ No",        callback_data=f"consent:no:{update.effective_chat.id}:{update.effective_user.id}")]
    ])
    await update.message.reply_text(CONSENT_MESSAGE, reply_markup=keyboard)

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(ChatJoinRequestHandler(on_join_request))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(CommandHandler("start", start_cmd))

    await app.initialize()
    await app.start()
    print("Bot running… (no logs mode)")
    await app.updater.start_polling(allowed_updates=["chat_join_request", "callback_query", "message"])
    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
