import os
import logging
import urllib.parse
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ── Config ──────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ── Gemini Setup ─────────────────────────────────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash-latest",
    system_instruction=(
        "You are a smart, helpful AI assistant inside a Telegram bot. "
        "Be concise, friendly, and helpful. Format responses clearly. "
        "Use emojis occasionally to keep things engaging."
    )
)

# ── Per-user chat sessions (memory) ─────────────────────────────────────
chat_sessions = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ── /start ───────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Hey {name}! I'm your AI assistant.\n\n"
        "I'm powered by Google Gemini for chat and Pollinations AI for images.\n\n"
        "📌 *What I can do:*\n"
        "💬 Chat with me about anything\n"
        "🎨 /imagine <prompt> — generate an image\n"
        "🗑️ /clear — reset our conversation\n"
        "❓ /help — see all commands\n\n"
        "Let's go! 🚀",
        parse_mode="Markdown"
    )


# ── /help ────────────────────────────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Commands:*\n\n"
        "/start — Welcome message\n"
        "/imagine <prompt> — Generate an image\n"
        "/clear — Clear conversation history\n"
        "/help — Show this message\n\n"
        "Just type normally to chat with me! 💬",
        parse_mode="Markdown"
    )


# ── /clear ───────────────────────────────────────────────────────────────
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in chat_sessions:
        del chat_sessions[user_id]
    await update.message.reply_text("🗑️ Conversation cleared! Fresh start.")


# ── /imagine ─────────────────────────────────────────────────────────────
async def imagine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)

    if not prompt:
        await update.message.reply_text(
            "❌ Please add a prompt!\n"
            "Example: `/imagine a cyberpunk city at night`",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text("🎨 Generating your image, hold on...")

    try:
        encoded = urllib.parse.quote(prompt)
        image_url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1024&height=1024&nologo=true&enhance=true"
        )
        await update.message.reply_photo(
            photo=image_url,
            caption=f"🎨 _{prompt}_",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await update.message.reply_text("⚠️ Couldn't generate the image. Try a different prompt.")


# ── Chat handler ─────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # Create session if new user
    if user_id not in chat_sessions:
        chat_sessions[user_id] = model.start_chat(history=[])

    try:
        response = chat_sessions[user_id].send_message(user_message)
        reply = response.text

        # Telegram max message length is 4096
        if len(reply) > 4096:
            for i in range(0, len(reply), 4096):
                await update.message.reply_text(reply[i:i+4096])
        else:
            await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"Gemini error: {e}")
        await update.message.reply_text(f"⚠️ Error: {str(e)}"
                                       )
    

# ── Main ─────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        raise ValueError("Missing TELEGRAM_TOKEN or GEMINI_API_KEY environment variables!")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("imagine", imagine))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    logger.info("✅ Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
