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
            url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page=1"
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    raise Exception(f"Status code: {response.status}")
                data = await response.json()
                cached_movies = data.get('results', [])
                last_fetch_time = datetime.now()
                logger.info(f"لیست با {len(cached_movies)} فیلم بروز شد")
                return True
    except Exception as e:
        logger.error(f"خطا در دریافت فیلم‌ها: {str(e)}")
        return False

async def get_movie_details(title):
    """دریافت جزئیات فیلم از OMDB"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    raise Exception(f"Status code: {response.status}")
                data = await response.json()
                if data.get('Response') != 'True':
                    return None
                return {
                    'title': data.get('Title', title),
                    'year': data.get('Year', 'N/A'),
                    'plot': data.get('Plot', 'بدون خلاصه'),
                    'imdb': data.get('imdbRating', 'N/A'),
                    'poster': data.get('Poster', 'N/A')
                }
    except Exception as e:
        logger.error(f"خطا در دریافت جزئیات: {str(e)}")
        return None

async def get_random_movie():
    """انتخاب تصادفی یک فیلم"""
    if not cached_movies or (datetime.now() - last_fetch_time).seconds > 3600:
        if not await fetch_movies():
            return None
    
    for _ in range(3):  # 3 بار تلاش برای یافتن فیلم
        movie = random.choice(cached_movies)
        title = movie.get('title') or movie.get('original_title')
        if not title:
            continue
        
        details = await get_movie_details(title)
        if details:
            try:
                imdb_score = float(details['imdb']) if details['imdb'] != 'N/A' else 0
                rating = min(5, max(1, int(imdb_score // 2)))
                return {
                    **details,
                    'rating': rating,
                    'special': imdb_score >= 8.0
                }
            except (ValueError, TypeError):
                continue
    
    return None

def format_movie(movie):
    """قالب‌بندی پیام فیلم"""
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie.get('special', False) else ''
    channel = "[🎬 کانال فیلم‌های برتر](https://t.me/bestwatch_channel)"
    
    return f"""
*{movie['title']}{special}*
📅 سال: {movie['year']}
🌟 امتیاز: {movie['imdb']}
📖 خلاصه: {movie['plot'][:200]}...
🎯 ارزش دیدن: {stars}

{channel}
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع"""
    if str(update.effective_user.id) == ADMIN_ID:
        await update.message.reply_text("ربات فعال است! از /post برای ارسال فیلم استفاده کنید")

async def post_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال فیلم به کانال"""
    if str(update.effective_user.id) != ADMIN_ID:
        return
    
    msg = await update.message.reply_text("🔍 در حال پیدا کردن فیلم مناسب...")
    movie = await get_random_movie()
    
    if not movie:
        await msg.edit_text("⚠️ متأسفانه فیلمی یافت نشد. لطفاً بعداً تلاش کنید")
        return
    
    try:
        caption = format_movie(movie)
        if movie['poster'] != 'N/A':
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=movie['poster'],
                caption=caption,
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=caption,
                parse_mode='Markdown'
            )
        await msg.edit_text(f"✅ فیلم «{movie['title']}» ارسال شد")
    except Exception as e:
        logger.error(f"ارسال فیلم ناموفق: {str(e)}")
        await msg.edit_text("❌ خطا در ارسال فیلم")

async def init_web_server():
    """سرور وب برای Render"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=PORT)
    await site.start()
    logger.info(f"سرور وب روی پورت {PORT} فعال شد")
    return runner

async def main():
    """تابع اصلی"""
    # ابتدا سرور وب را راه‌اندازی کنید
    web_runner = await init_web_server()
    
    # سپس ربات تلگرام را راه‌اندازی کنید
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("post", post_movie))
    
    await application.initialize()
    await application.start()
    logger.info("🤖 ربات تلگرام آماده به کار!")
    
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await application.stop()
        await web_runner.cleanup()
        logger.info("ربات با موفقیت متوقف شد")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("ربات متوقف شد")
