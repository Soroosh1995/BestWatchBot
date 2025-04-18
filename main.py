import asyncio
import os
import logging
import aiohttp
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from datetime import datetime
from aiohttp import web

# --- تنظیمات اولیه ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- بارگذاری تنظیمات ---
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
ADMIN_ID = os.getenv('ADMIN_ID')
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
PORT = int(os.getenv('PORT', 8080))  # پورت اجباری برای Render

# --- کش فیلم‌ها ---
cached_movies = []
last_fetch_time = None

async def health_check(request):
    """Endpoint سلامت برای Render"""
    return web.Response(text="OK")

async def fetch_movies():
    """دریافت فیلم‌های پرطرفدار از TMDB"""
    global cached_movies, last_fetch_time
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}"
            async with session.get(url) as response:
                data = await response.json()
                cached_movies = data.get('results', [])
                last_fetch_time = datetime.now()
                logger.info(f"لیست فیلم‌ها با {len(cached_movies)} فیلم بروز شد")
                return True
    except Exception as e:
        logger.error(f"خطا در دریافت فیلم‌ها: {e}")
        return False

async def get_movie_details(title):
    """دریافت جزئیات فیلم از OMDB"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            async with session.get(url) as response:
                data = await response.json()
                if data.get('Response') == 'True':
                    return {
                        'title': data.get('Title', title),
                        'year': data.get('Year', 'N/A'),
                        'plot': data.get('Plot', 'بدون خلاصه'),
                        'imdb': data.get('imdbRating', 'N/A'),
                        'poster': data.get('Poster', 'N/A')
                    }
                return None
    except Exception as e:
        logger.error(f"خطا در دریافت جزئیات فیلم: {e}")
        return None

async def get_random_movie():
    """انتخاب تصادفی یک فیلم"""
    if not cached_movies or (datetime.now() - last_fetch_time).seconds > 3600:
        await fetch_movies()
    
    if not cached_movies:
        return None
    
    movie = random.choice(cached_movies)
    details = await get_movie_details(movie.get('title', ''))
    
    if not details:
        return None
    
    try:
        imdb_score = float(details['imdb']) if details['imdb'] != 'N/A' else 0
        rating = min(5, max(1, int(imdb_score // 2)))
    except:
        rating = 3
    
    return {
        **details,
        'rating': rating,
        'special': imdb_score >= 8.0
    }

def format_movie(movie):
    """قالب‌بندی پیام فیلم"""
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie['special'] else ''
    channel = "[کانال فیلم‌های برتر](https://t.me/bestwatch_channel)"
    
    return f"""
*🎬 {movie['title']}{special}*
*📅 سال:* {movie['year']}
*🌟 امتیاز IMDB:* {movie['imdb']}
*📖 خلاصه:* {movie['plot'][:200]}...
*🎯 ارزش دیدن:* {stars}

{channel}
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع"""
    if str(update.effective_user.id) == ADMIN_ID:
        await update.message.reply_text("""
سلام ادمین گرامی! 🤖

دستورات موجود:
/post - ارسال فیلم تصادفی
/fetch - بروزرسانی لیست فیلم‌ها
""", parse_mode='Markdown')

async def post_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال فیلم به کانال"""
    if str(update.effective_user.id) != ADMIN_ID:
        return
    
    msg = await update.message.reply_text("در حال آماده‌سازی فیلم...")
    movie = await get_random_movie()
    
    if not movie:
        await msg.edit_text("⚠️ خطا در یافتن فیلم مناسب")
        return
    
    try:
        if movie['poster'] != 'N/A':
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=movie['poster'],
                caption=format_movie(movie),
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=format_movie(movie),
                parse_mode='Markdown'
            )
        await msg.edit_text(f"✅ فیلم '{movie['title']}' با موفقیت ارسال شد")
    except Exception as e:
        logger.error(f"خطا در ارسال فیلم: {e}")
        await msg.edit_text("❌ خطا در ارسال فیلم")

async def fetch_movies_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بروزرسانی دستی لیست فیلم‌ها"""
    if str(update.effective_user.id) != ADMIN_ID:
        return
    
    msg = await update.message.reply_text("در حال بروزرسانی لیست فیلم‌ها...")
    if await fetch_movies():
        await msg.edit_text(f"✅ لیست با {len(cached_movies)} فیلم بروز شد")
    else:
        await msg.edit_text("❌ خطا در بروزرسانی لیست")

async def init_web_server():
    """راه‌اندازی سرور وب برای Render"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=PORT)
    await site.start()
    logger.info(f"سرور وب روی پورت {PORT} شروع شد")
    return runner

async def main():
    """تابع اصلی"""
    # بارگذاری اولیه فیلم‌ها
    await fetch_movies()
    
    # راه‌اندازی سرور وب
    web_runner = await init_web_server()
    
    # ساخت ربات تلگرام
    app = Application.builder().token(TOKEN).build()
    
    # ثبت دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("post", post_movie))
    app.add_handler(CommandHandler("fetch", fetch_movies_cmd))
    
    # شروع ربات
    await app.initialize()
    await app.start()
    logger.info("🤖 ربات فعال شد!")
    
    # اجرای نامحدود
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await app.stop()
        await web_runner.cleanup()
        logger.info("ربات متوقف شد")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("ربات متوقف شد")
