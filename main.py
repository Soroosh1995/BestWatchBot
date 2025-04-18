import asyncio
import os
import logging
import aiohttp
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from datetime import datetime

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

# --- کش فیلم‌ها ---
cached_movies = []
last_fetch_time = None

async def get_movie_info(title):
    """دریافت اطلاعات فیلم از OMDB"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            async with session.get(url) as response:
                data = await response.json()
                if data.get('Response') == 'True':
                    return {
                        'title': data['Title'],
                        'year': data['Year'],
                        'plot': data['Plot'],
                        'imdb': data['imdbRating'],
                        'poster': data['Poster']
                    }
                return None
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات فیلم: {e}")
        return None

async def fetch_popular_movies():
    """دریافت فیلم‌های پرطرفدار از TMDB"""
    global cached_movies, last_fetch_time
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}"
            async with session.get(url) as response:
                data = await response.json()
                cached_movies = data.get('results', [])
                last_fetch_time = datetime.now()
                return True
    except Exception as e:
        logger.error(f"خطا در دریافت فیلم‌ها: {e}")
        return False

async def get_random_movie():
    """انتخاب تصادفی یک فیلم"""
    if not cached_movies or (datetime.now() - last_fetch_time).seconds > 86400:
        await fetch_popular_movies()
    
    if not cached_movies:
        return None
    
    movie = random.choice(cached_movies)
    details = await get_movie_info(movie['title'])
    
    if not details:
        return None
    
    # محاسبه امتیاز (1-5 ستاره)
    imdb_score = float(details['imdb']) if details['imdb'] != 'N/A' else 0
    rating = min(5, max(1, int(imdb_score // 2)))
    
    return {
        **details,
        'rating': rating,
        'special': imdb_score >= 8.0
    }

def format_movie_message(movie):
    """فرمت‌دهی پیام فیلم"""
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie['special'] else ''
    channel_link = '[کانال فیلم‌های برتر](https://t.me/bestwatch_channel)'
    
    return f"""
*🎬 {movie['title']}{special}*
*📅 سال انتشار:* {movie['year']}
*🌟 امتیاز IMDB:* {movie['imdb']}
*📖 خلاصه داستان:* {movie['plot'][:300]}...
*🎯 امتیاز ما:* {stars}

{channel_link}
"""

async def post_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال یک فیلم تصادفی"""
    if str(update.effective_user.id) != ADMIN_ID:
        return
    
    msg = await update.message.reply_text("در حال آماده‌سازی...")
    movie = await get_random_movie()
    
    if not movie:
        await msg.edit_text("خطا در یافتن فیلم مناسب")
        return
    
    try:
        if movie['poster'] and movie['poster'] != 'N/A':
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=movie['poster'],
                caption=format_movie_message(movie),
                parse_mode='MarkdownV2'
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=format_movie_message(movie),
                parse_mode='MarkdownV2'
            )
        await msg.edit_text("فیلم با موفقیت ارسال شد!")
    except Exception as e:
        logger.error(f"خطا در ارسال فیلم: {e}")
        await msg.edit_text("خطا در ارسال فیلم")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع"""
    await update.message.reply_text('سلام! از /post برای ارسال فیلم استفاده کن')

async def main():
    """ورودی اصلی برنامه"""
    await fetch_popular_movies()
    
    app = Application.builder().token(TOKEN).build()
    
    # ثبت دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("post", post_movie))
    
    # شروع ربات
    await app.initialize()
    await app.start()
    logger.info("ربات فعال و آماده به کار!")
    
    # اجرای نامحدود
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("ربات متوقف شد")
