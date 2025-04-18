import asyncio
import os
import logging
import aiohttp
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, JobQueue
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
PORT = int(os.getenv('PORT', 8080))  # استفاده از پورت 8080 از env

# --- کش فیلم‌ها ---
cached_movies = []
last_fetch_time = None

async def health_check(request):
    """Endpoint سلامت برای Render"""
    return web.Response(text="OK")

async def get_movie_info(title):
    """دریافت اطلاعات فیلم از OMDB و TMDB"""
    try:
        async with aiohttp.ClientSession() as session:
            omdb_url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            async with session.get(omdb_url) as response:
                omdb_data = await response.json()
                
                if omdb_data.get('Response') != 'True':
                    return None
                
                tmdb_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
                async with session.get(tmdb_url) as tmdb_response:
                    tmdb_data = await tmdb_response.json()
                    
                    trailer = "N/A"
                    if tmdb_data.get('results'):
                        movie_id = tmdb_data['results'][0]['id']
                        videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
                        async with session.get(videos_url) as videos_response:
                            videos_data = await videos_response.json()
                            if videos_data.get('results'):
                                for video in videos_data['results']:
                                    if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                        trailer = f"https://www.youtube.com/watch?v={video['key']}"
                                        break
                    
                    return {
                        'title': omdb_data.get('Title', title),
                        'year': omdb_data.get('Year', 'N/A'),
                        'plot': omdb_data.get('Plot', 'بدون خلاصه'),
                        'imdb': omdb_data.get('imdbRating', 'N/A'),
                        'rotten_tomatoes': next(
                            (r['Value'] for r in omdb_data.get('Ratings', [])
                            if r['Source'] == 'Rotten Tomatoes'), 'N/A'),
                        'trailer': trailer,
                        'poster': omdb_data.get('Poster', 'N/A')
                    }
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات فیلم: {e}")
        return None

async def fetch_popular_movies():
    """بروزرسانی لیست فیلم‌های پرطرفدار"""
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
        logger.error(f"خطا در بروزرسانی فیلم‌ها: {e}")
        return False

async def get_random_movie():
    """انتخاب تصادفی یک فیلم با جزئیات کامل"""
    if not cached_movies or (datetime.now() - last_fetch_time).seconds > 86400:
        await fetch_popular_movies()
    
    if not cached_movies:
        return None
    
    movie = random.choice(cached_movies)
    details = await get_movie_info(movie.get('title', ''))
    
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
        'special': imdb_score >= 8.0 if 'imdb_score' in locals() else False
    }

def format_movie_post(movie):
    """فرمت‌دهی پیام نهایی"""
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie.get('special', False) else ''
    channel_link = '[🎬 کانال فیلم‌های برتر](https://t.me/bestwatch_channel)'
    
    return f"""
*🎬 {movie['title']}{special}*
*📅 سال:* {movie['year']}
*🌟 امتیازها:* 
- IMDB: {movie['imdb']}
- Rotten Tomatoes: {movie['rotten_tomatoes']}
*📖 خلاصه:* {movie['plot'][:250]}...
*🎞 تریلر:* {movie['trailer']}
*🎯 ارزش دیدن:* {stars}

{channel_link}
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع برای ادمین"""
    if str(update.effective_user.id) == ADMIN_ID:
        await update.message.reply_text("""
🤖 *دستورات مدیریتی:*
/fetch - بروزرسانی لیست فیلم‌ها
/post - ارسال فیلم تصادفی به کانال
/autopost - فعال‌سازی ارسال خودکار
""", parse_mode='MarkdownV2')

async def fetch_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بروزرسانی دستی لیست فیلم‌ها"""
    if str(update.effective_user.id) == ADMIN_ID:
        msg = await update.message.reply_text("در حال بروزرسانی لیست فیلم‌ها...")
        if await fetch_popular_movies():
            await msg.edit_text(f"✅ لیست با {len(cached_movies)} فیلم بروز شد")
        else:
            await msg.edit_text("❌ خطا در بروزرسانی")

async def post_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال دستی فیلم به کانال"""
    if str(update.effective_user.id) != ADMIN_ID:
        return
    
    msg = await update.message.reply_text("در حال انتخاب فیلم...")
    movie = await get_random_movie()
    
    if not movie:
        await msg.edit_text("❌ خطا در یافتن فیلم")
        return
    
    try:
        if movie['poster'] != 'N/A':
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=movie['poster'],
                caption=format_movie_post(movie),
                parse_mode='MarkdownV2'
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=format_movie_post(movie),
                parse_mode='MarkdownV2'
            )
        await msg.edit_text(f"✅ فیلم {movie['title']} ارسال شد")
    except Exception as e:
        logger.error(f"خطا در ارسال فیلم: {e}")
        await msg.edit_text("❌ خطا در ارسال فیلم")

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    """ارسال خودکار فیلم"""
    movie = await get_random_movie()
    if movie:
        try:
            if movie['poster'] != 'N/A':
                await context.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=movie['poster'],
                    caption=format_movie_post(movie),
                    parse_mode='MarkdownV2'
                )
            else:
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=format_movie_post(movie),
                    parse_mode='MarkdownV2'
                )
            logger.info(f"فیلم {movie['title']} به صورت خودکار ارسال شد")
        except Exception as e:
            logger.error(f"خطا در ارسال خودکار: {e}")

async def setup_autopost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم ارسال خودکار"""
    if str(update.effective_user.id) != ADMIN_ID:
        return
    
    if not hasattr(context.application, 'job_queue'):
        context.application.job_queue = JobQueue()
        context.application.job_queue.set_application(context.application)
    
    context.application.job_queue.run_repeating(auto_post, interval=3600, first=10)
    await update.message.reply_text("✅ ارسال خودکار فعال شد (هر 1 ساعت)")

async def init_web_server():
    """راه‌اندازی سرور وب برای Render"""
    app_web = web.Application()
    app_web.router.add_get('/health', health_check)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=PORT)
    await site.start()
    logger.info(f"سرور وب روی پورت {PORT} شروع شد")
    return runner

async def main():
    """ورودی اصلی برنامه"""
    # بارگذاری اولیه فیلم‌ها
    await fetch_popular_movies()
    
    # ساخت برنامه تلگرام
    app = Application.builder().token(TOKEN).build()
    
    # ثبت دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fetch", fetch_movies))
    app.add_handler(CommandHandler("post", post_movie))
    app.add_handler(CommandHandler("autopost", setup_autopost))
    
    # شروع ربات
    await app.initialize()
    await app.start()
    
    # راه‌اندازی سرور وب
    runner = await init_web_server()
    
    logger.info("🤖 ربات آماده به کار!")
    
    # اجرای نامحدود
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await app.stop()
        await runner.cleanup()
        logger.info("ربات متوقف شد")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("ربات با Ctrl+C متوقف شد")
