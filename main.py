import os
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    ApplicationBuilder
)
from bot.utils import fetchmovies, post_to_channel, get_random_movie

PORT = int(os.environ.get("PORT", 8443))

# لاگر برای نمایش خطاها در Render
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 به Best Watch خوش اومدی!\n\n"
        "دستورات موجود:\n"
        "/addmovie - اضافه کردن فیلم\n"
        "/postnow - ارسال فوری یک فیلم به کانال\n"
        "/start - نمایش این پیام"
    )

# /addmovie
async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movie = await get_random_movie()
    if movie:
        context.bot_data.setdefault("movies", []).append(movie)
        await update.message.reply_text(f"✅ فیلم اضافه شد: {movie['title']}")
    else:
        await update.message.reply_text("❌ نتونستم فیلمی پیدا کنم.")

# /postnow
async def postnow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movies = context.bot_data.get("movies", [])
    if not movies:
        await update.message.reply_text("⚠️ لیست فیلم‌ها خالیه!")
        return
    movie = movies.pop(0)
    await post_to_channel(movie, context.bot)
    await update.message.reply_text(f"✅ پست ارسال شد: {movie['title']}")

# Job برای ارسال خودکار
async def send_post(context: ContextTypes.DEFAULT_TYPE):
    movies = context.bot_data.get("movies", [])
    if not movies:
        logger.info("🎬 لیست فیلم خالیه. فیلمی برای ارسال نیست.")
        return
    movie = movies.pop(0)
    await post_to_channel(movie, context.bot)
    logger.info(f"✅ پست ارسال شد: {movie['title']}")

# Startup: بارگذاری اولیه لیست فیلم
async def on_startup(application: Application):
    await fetchmovies(application)
    logger.info("🎬 فیلم اولیه با موفقیت لود شد.")

# اجرای اصلی
def main():
    TOKEN = os.getenv("BOT_TOKEN")
    HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

    application = ApplicationBuilder().token(TOKEN).build()

    # دستورات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addmovie", add_movie))
    application.add_handler(CommandHandler("postnow", postnow))

    # Job برای ارسال هر 10 دقیقه
    application.job_queue.run_repeating(send_post, interval=600, first=10)

    # اجرای Webhook با Startup
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"https://{HOSTNAME}/",
        on_startup=[on_startup]
    )

if __name__ == "__main__":
    main()
