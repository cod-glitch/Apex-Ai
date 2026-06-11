import os
import logging
import urllib.parse
import aiohttp
import google.generativeai as genai
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ── Config ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))  # Your Telegram user ID for broadcast

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is missing!")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing!")

# ── Gemini Setup ──────────────────────────────────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)

def get_model():
    today = datetime.now().strftime("%A, %B %d, %Y")
    return genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
    
        system_instruction=(
            f"You are a smart, helpful AI assistant inside a Telegram bot. "
            f"Be concise, friendly, and helpful. Format responses clearly. "
            f"Use emojis occasionally to keep things engaging. "
            f"Today's date is {today}. "
            f"You have access to Google Search so use it for current events, news, sports, prices, weather or anything that needs up to date information. "
            f"If asked about recent events, be honest that you may not have the latest info and suggest the user verify online."
            f"Never say your knowledge cuts off in 2014 — that is incorrect."
            f"You have knowledge up to early 2026. If asked about recent events, be honest that you may not have the latest info."
        )
    )

# ── Storage ───────────────────────────────────────────────────────────────
chat_sessions = {}
all_users = set()  # Track all user IDs for broadcast

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ── /start ────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    all_users.add(user.id)
    await update.message.reply_text(
        f"👋 Hey {user.first_name}! I'm your AI assistant.\n\n"
        "🧠 Powered by Gemini AI + Google Search + Pollinations\n\n"
        "📌 *What I can do:*\n"
        "💬 Chat about anything (with live web search)\n"
        "🎨 /imagine <prompt> — generate an image\n"
        "🖼️ Send me a photo — I'll analyze it\n"
        "🗑️ /clear — reset our conversation\n"
        "❓ /help — see all commands\n\n"
        "Let's go! 🚀",
        parse_mode="Markdown"
    )


# ── /help ─────────────────────────────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_users.add(update.effective_user.id)
    await update.message.reply_text(
        "🤖 *Commands:*\n\n"
        "/start — Welcome message\n"
        "/imagine <prompt> — Generate an image\n"
        "/clear — Clear conversation history\n"
        "/help — Show this message\n\n"
        "🖼️ Send any photo for image analysis\n"
        "💬 Just type to chat with live web search!",
        parse_mode="Markdown"
    )


# ── /clear ────────────────────────────────────────────────────────────────
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in chat_sessions:
        del chat_sessions[user_id]
    await update.message.reply_text("🗑️ Conversation cleared! Fresh start.")


# ── /imagine ──────────────────────────────────────────────────────────────
async def imagine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_users.add(update.effective_user.id)
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
        hf_key = os.environ.get("HF_API_KEY", "")
        api_url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
        headers = {"Authorization": f"Bearer {hf_key}"}
        payload = {"inputs": prompt}

        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    image_data = await resp.read()
                    await update.message.reply_photo(
                        photo=image_data,
                        caption=f"🎨 _{prompt}_",
                        parse_mode="Markdown"
                    )
                else:
                    error = await resp.text()
                    await update.message.reply_text(f"⚠️ Error {resp.status}: {error[:200]}")
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await update.message.reply_text(f"⚠️ Image error: {str(e)}")


# ── /broadcast (admin only) ───────────────────────────────────────────────
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("❌ Please provide a message!\nExample: /broadcast Hello everyone!")
        return

    if not all_users:
        await update.message.reply_text("⚠️ No users to broadcast to yet.")
        return

    sent = 0
    failed = 0
    await update.message.reply_text(f"📢 Broadcasting to {len(all_users)} users...")

    for uid in all_users:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 *Announcement:*\n\n{message}",
                parse_mode="Markdown"
            )
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send to {uid}: {e}")
            failed += 1

    await update.message.reply_text(
        f"✅ Broadcast complete!\n"
        f"Sent: {sent} | Failed: {failed}"
    )


# ── Image analysis handler ────────────────────────────────────────────────
async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_users.add(update.effective_user.id)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    photo = update.message.photo[-1]  # Get highest resolution
    caption = update.message.caption or "Describe this image in detail and answer any questions about it."

    try:
        file = await context.bot.get_file(photo.file_id)
        async with aiohttp.ClientSession() as session:
            async with session.get(file.file_path) as resp:
                image_bytes = await resp.read()

        import base64
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        vision_model = genai.GenerativeModel("gemini-2.5-flash-lite")
        response = vision_model.generate_content([
            {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": image_b64
                }
            },
            caption
        ])

        reply = response.text
        if len(reply) > 4096:
            for i in range(0, len(reply), 4096):
                await update.message.reply_text(reply[i:i+4096])
        else:
            await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"Image analysis error: {e}")
        await update.message.reply_text(f"⚠️ Couldn't analyze the image: {str(e)}")


# ── Chat handler ──────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    all_users.add(user_id)
    user_message = update.message.text

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    if user_id not in chat_sessions:
        chat_sessions[user_id] = get_model().start_chat(history=[])

    try:
        response = chat_sessions[user_id].send_message(user_message)

        # Extract text from response (handle grounding/search responses)
        reply = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                reply += part.text

        if not reply:
            reply = "⚠️ I couldn't generate a response. Try again."

        # Telegram max message length is 4096
        if len(reply) > 4096:
            for i in range(0, len(reply), 4096):
                await update.message.reply_text(reply[i:i+4096])
        else:
            await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"Gemini error: {e}")
        await update.message.reply_text(f"⚠️ Error: {str(e)}")


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("imagine", imagine))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.PHOTO, analyze_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    logger.info("✅ Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
