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
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 8080))

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
            async with session.get(url, timeout=10) as response:
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

async def generate_analysis(title):
    """تولید تحلیل با OpenAI"""
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{
                "role": "user",
                "content": f"تحلیل کوتاه و جذاب درباره فیلم {title} به زبان فارسی (حدود 100 کلمه)"
            }],
            "temperature": 0.7,
            "max_tokens": 200
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            ) as response:
                data = await response.json()
                return data['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"خطا در تولید تحلیل: {str(e)}")
        return "تحلیل در دسترس نیست"

async def get_random_movie():
    """انتخاب تصادفی یک فیلم"""
    if not cached_movies or (datetime.now() - last_fetch_time).seconds > 3600:
        if not await fetch_movies():
            return None
    
    for _ in range(3):  # 3 بار تلاش
        movie = random.choice(cached_movies)
        title = movie.get('title') or movie.get('original_title')
        if not title:
            continue
        
        details = await get_movie_details(title)
        if details:
            try:
                imdb_score = float(details['imdb']) if details['imdb'] != 'N/A' else 0
                rating = min(5, max(1, int(imdb_score // 2)))
                analysis = await generate_analysis(title)
                return {
                    **details,
                    'rating': rating,
                    'special': imdb_score >= 8.0,
                    'analysis': analysis
                }
            except (ValueError, TypeError) as e:
                logger.error(f"خطا در پردازش امتیاز: {str(e)}")
                continue
    
    return None

def format_movie(movie):
    """قالب‌بندی پیام فیلم"""
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie.get('special') else ''
    
    return f"""
*🎬 {movie['title']}{special}*
📅 سال: {movie['year']}
🌟 امتیاز: {movie['imdb']}
📖 خلاصه: {movie['plot'][:200]}...
🍿 تحلیل: {movie['analysis']}
🎯 ارزش دیدن: {stars}

[📺 کانال ما](https://t.me/bestwatch_channel)
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع"""
    await update.message.reply_text("ربات فعال است! از /post استفاده کنید")

async def post_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال فیلم به کانال"""
    if str(update.effective_user.id) != ADMIN_ID:
        return
    
    msg = await update.message.reply_text("در حال آماده‌سازی...")
    movie = await get_random_movie()
    
    if not movie:
        await msg.edit_text("⚠️ خطا در یافتن فیلم")
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
        await msg.edit_text(f"✅ فیلم ارسال شد: {movie['title']}")
    except Exception as e:
        logger.error(f"خطا در ارسال: {str(e)}")
        await msg.edit_text("❌ ارسال ناموفق")

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
    # راه‌اندازی سرور وب
    web_runner = await init_web_server()
    
    # راه‌اندازی ربات تلگرام
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("post", post_movie))
    
    await app.initialize()
    await app.start()
    logger.info("🤖 ربات آماده به کار!")
    
    # اجرای نامحدود
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("ربات متوقف شد")
