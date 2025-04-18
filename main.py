import telegram
import asyncio
import os
import logging
import aiohttp
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from aiohttp import web
import re
from datetime import datetime, time

# --- تنظیمات اولیه ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
ADMIN_ID = os.getenv('ADMIN_ID')
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
PORT = int(os.getenv('PORT', 8080))

# --- کش فیلم‌ها ---
cached_movies = []
last_fetch_time = None

# --- توابع کمکی ---
def clean_text(text):
    text = re.sub(r'[^\w\s\-\.\,\!\?\:\(\)\'\"]', '', text)
    return text[:300]

async def get_movie_info(title):
    """دریافت اطلاعات فیلم از OMDB و TMDB"""
    try:
        async with aiohttp.ClientSession() as session:
            # دریافت اطلاعات از OMDB
            omdb_url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            async with session.get(omdb_url, timeout=15) as response:
                omdb_data = await response.json()
                
                if omdb_data.get('Response') == 'True':
                    # دریافت اطلاعات از TMDB برای تریلر
                    search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
                    async with session.get(search_url, timeout=15) as tmdb_response:
                        tmdb_data = await tmdb_response.json()
                        
                        trailer = "N/A"
                        if tmdb_data.get('results'):
                            movie_id = tmdb_data['results'][0]['id']
                            videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
                            async with session.get(videos_url, timeout=15) as videos_response:
                                videos_data = await videos_response.json()
                                if videos_data.get('results'):
                                    for video in videos_data['results']:
                                        if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                            trailer = f"https://www.youtube.com/watch?v={video['key']}"
                                            break
                    
                    # پردازش خلاصه داستان (محدود به 2 جمله)
                    plot = '. '.join(omdb_data.get('Plot', 'خلاصه‌ای موجود نیست').split('.')[:2])
                    
                    # پردازش امتیازها
                    imdb_rating = f"{float(omdb_data.get('imdbRating', 0)):.1f}/10"
                    rt_rating = next(
                        (r['Value'] for r in omdb_data.get('Ratings', []) 
                         if r['Source'] == 'Rotten Tomatoes'), 'N/A')
                    
                    return {
                        'title': omdb_data.get('Title', title),
                        'year': omdb_data.get('Year', 'N/A'),
                        'plot': plot,
                        'imdb': imdb_rating,
                        'rotten_tomatoes': rt_rating,
                        'trailer': trailer,
                        'poster': omdb_data.get('Poster', 'N/A')
                    }
                return None
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات فیلم: {e}")
        return None

async def generate_comment(title):
    """تولید تحلیل حرفه‌ای با OpenAI"""
    try:
        prompt = f"""
        تحلیل دقیق و کامل درباره فیلم {title} به زبان فارسی (حدود 150 کلمه):
        1. معرفی کلی فیلم و ژانر
        2. بررسی نقاط قوت (داستان، بازیگری، کارگردانی)
        3. بررسی نقاط ضعف (اگر دارد)
        4. جمع‌بندی و توصیه نهایی
        لطفاً تحلیل را مفصل و با جزئیات بنویسید.
        """
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY.strip()}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 350
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=40
            ) as response:
                data = await response.json()
                return data['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"خطا در تولید تحلیل: {e}")
        return "این فیلم اثری قابل تأمل با اجرای خوب بازیگران است که ارزش تماشا دارد."

async def fetch_movies_to_cache():
    global cached_movies, last_fetch_time
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page=1"
            async with session.get(url, timeout=15) as response:
                data = await response.json()
                if 'results' in data and data['results']:
                    cached_movies = data['results']
                    last_fetch_time = datetime.now()
                    logger.info(f"لیست فیلم‌ها آپدیت شد. تعداد: {len(cached_movies)}")
                    return True
                logger.error("خطا در دریافت لیست از TMDB")
                return False
    except Exception as e:
        logger.error(f"خطا در آپدیت لیست: {e}")
        return False

async def get_random_movie():
    try:
        if not cached_movies or (datetime.now() - last_fetch_time).seconds > 86400:
            await fetch_movies_to_cache()
            
        movie = random.choice(cached_movies)
        movie_info = await get_movie_info(movie['title'])
        if not movie_info:
            return None
            
        comment = await generate_comment(movie['title'])
        imdb_score = float(movie_info['imdb'].split('/')[0]) if movie_info['imdb'] != 'N/A' else 0
        rating = min(5, max(1, int(imdb_score // 2)))
        
        return {
            **movie_info,
            'comment': comment,
            'rating': rating,
            'special': imdb_score >= 8.0
        }
    except Exception as e:
        logger.error(f"خطا در انتخاب فیلم: {e}")
        return None

def format_movie_post(movie):
    rating_stars = {5: '⭐️⭐️⭐️⭐️⭐️', 4: '⭐️⭐️⭐️⭐️', 3: '⭐️⭐️⭐️', 2: '⭐️⭐️', 1: '⭐️'}
    special_symbol = ' 👑' if movie.get('special', False) else ''
    post = (
        f"<b>🎬 عنوان فیلم:</b> {movie['title']}{special_symbol}\n\n"
        f"<b>📅 سال تولید:</b> {movie['year']}\n\n"
        f"<b>📝 خلاصه داستان:</b>\n{movie['plot']}\n\n"
        f"<b>🌟 امتیاز:</b>\nIMDB: {movie['imdb']}\nRotten Tomatoes: {movie['rotten_tomatoes']}\n\n"
        f"<b>🎞 لینک تریلر:</b>\n{movie['trailer']}\n\n"
        f"<b>🍿 تحلیل ما:</b>\n{movie['comment']}\n\n"
        f"<b>🎯 ارزش دیدن:</b> {rating_stars[movie['rating']]}\n\n"
        f"<a href='https://t.me/bestwatch_channel'>کانال ما</a>"
    )
    return post

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("❌ این بات فقط برای ادمین قابل استفاده است!")
        return
    
    commands = [
        "/fetchmovies - آپدیت لیست فیلم‌ها",
        "/postnow - پست فوری فیلم"
    ]
    await update.message.reply_text(
        "🤖 به پنل ادمین خوش آمدید!\n\n" +
        "📜 دستورات:\n" + "\n".join(commands)
    )

async def fetch_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("❌ فقط ادمین می‌تواند این دستور را اجرا کند!")
        return
    
    await update.message.reply_text("در حال دریافت لیست جدید از TMDB...")
    if await fetch_movies_to_cache():
        await update.message.reply_text(f"✅ لیست فیلم‌ها آپدیت شد! (تعداد: {len(cached_movies)})")
    else:
        await update.message.reply_text("❌ خطا در آپدیت لیست فیلم‌ها!")

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("❌ فقط ادمین می‌تواند این دستور را اجرا کند!")
        return
        
    await update.message.reply_text("در حال آماده‌سازی پست...")
    movie = await get_random_movie()
    if not movie:
        await update.message.reply_text("⚠️ خطا: هیچ فیلمی پیدا نشد! از /fetchmovies استفاده کن.")
        return
        
    post = format_movie_post(movie)
    try:
        if movie['poster'] != 'N/A':
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=movie['poster'],
                caption=post,
                parse_mode='HTML'
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=post,
                parse_mode='HTML'
            )
        await update.message.reply_text(f"✅ پست فیلم {movie['title']} ارسال شد!")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ارسال پست: {str(e)}")

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    logger.info("در حال اجرای پست خودکار...")
    movie = await get_random_movie()
    if not movie:
        logger.error("⚠️ خطا در پست خودکار: هیچ فیلمی پیدا نشد!")
        return
        
    post = format_movie_post(movie)
    try:
        if movie['poster'] != 'N/A':
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=movie['poster'],
                caption=post,
                parse_mode='HTML'
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=post,
                parse_mode='HTML'
            )
        logger.info(f"✅ پست خودکار ارسال شد: {movie['title']}")
    except Exception as e:
        logger.error(f"❌ خطا در پست خودکار: {str(e)}")

async def health_check(request):
    return web.Response(text="OK")

async def main():
    # ابتدا کش را پر کنید
    if not await fetch_movies_to_cache():
        logger.error("❌ خطا در دریافت اولیه لیست فیلم‌ها!")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fetchmovies", fetch_movies))
    app.add_handler(CommandHandler("postnow", post_now))

    if app.job_queue:
        app.job_queue.run_repeating(auto_post, interval=600, first=10)
        app.job_queue.run_daily(fetch_movies_to_cache, time=time(hour=0))
        logger.info("✅ JobQueue فعال شد!")
    else:
        logger.error("❌ JobQueue غیرفعال است!")

    # سرور سلامت برای Render
    web_app = web.Application()
    web_app.add_routes([web.get('/health', health_check)])
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    await app.initialize()
    await app.start()
    logger.info("🤖 بات فعال شد!")
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
