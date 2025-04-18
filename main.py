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
    return text[:1000]

async def get_movie_info(title):
    """دریافت اطلاعات فیلم از OMDB و TMDB"""
    try:
        async with aiohttp.ClientSession() as session:
            # دریافت اطلاعات پایه از OMDB
            omdb_url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            async with session.get(omdb_url, timeout=15) as omdb_response:
                omdb_data = await omdb_response.json()
                
                if omdb_data.get('Response') == 'True':
                    # دریافت اطلاعات تکمیلی از TMDB
                    tmdb_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
                    async with session.get(tmdb_url, timeout=15) as tmdb_response:
                        tmdb_data = await tmdb_response.json()
                        
                        # یافتن تریلر
                        trailer_url = "N/A"
                        if tmdb_data.get('results'):
                            movie_id = tmdb_data['results'][0]['id']
                            videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
                            async with session.get(videos_url, timeout=15) as videos_response:
                                videos_data = await videos_response.json()
                                if videos_data.get('results'):
                                    for video in videos_data['results']:
                                        if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                            trailer_url = f"https://www.youtube.com/watch?v={video['key']}"
                                            break
                        
                        # پردازش امتیازها
                        imdb_rating = omdb_data.get('imdbRating', 'N/A')
                        rt_rating = 'N/A'
                        if 'Ratings' in omdb_data:
                            for rating in omdb_data['Ratings']:
                                if rating['Source'] == 'Rotten Tomatoes':
                                    rt_rating = rating['Value']
                                    break
                        
                        return {
                            'title': omdb_data.get('Title', title),
                            'year': omdb_data.get('Year', 'N/A'),
                            'plot': omdb_data.get('Plot', 'خلاصه‌ای موجود نیست.'),
                            'imdb': imdb_rating,
                            'rotten_tomatoes': rt_rating,
                            'trailer': trailer_url,
                            'poster': omdb_data.get('Poster', 'N/A')
                        }
                return None
    except Exception as e:
        logger.error(f"خطا در get_movie_info: {e}")
        return None

async def generate_comment(title):
    """تولید تحلیل حرفه‌ای با OpenAI"""
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "تحلیل حرفه‌ای و جذاب درباره فیلم بنویس (حدود 100-120 کلمه). از اصطلاحات سینمایی استفاده کن و نقاط قوت و ضعف اثر را بررسی کن."
                    },
                    {
                        "role": "user",
                        "content": f"تحلیل دقیق درباره فیلم {title}"
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 200
            }
            async with session.post(url, json=payload, headers=headers, timeout=30) as response:
                data = await response.json()
                return data['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"خطا در generate_comment: {e}")
        return "این فیلم اثری قابل تأمل با اجرای خوب بازیگران است."

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
                else:
                    logger.error("خطا در دریافت لیست از TMDB: results خالی است!")
    except Exception as e:
        logger.error(f"خطا در fetch_movies_to_cache: {e}")

async def get_random_movie():
    try:
        if not cached_movies or (last_fetch_time and (datetime.now() - last_fetch_time).seconds >= 86400):
            await fetch_movies_to_cache()
            
        if not cached_movies:
            logger.error("لیست فیلم‌ها خالی است!")
            return None
            
        movie = random.choice(cached_movies)
        title = movie.get('title', 'فیلم ناشناخته')
        movie_info = await get_movie_info(title)
        
        if not movie_info:
            return None
        
        comment = await generate_comment(title)
        imdb_score = float(movie_info['imdb']) if movie_info['imdb'] != 'N/A' else 0
        rating = min(5, max(1, int(imdb_score // 2)))
        special = imdb_score >= 8.0
        
        return {
            'title': movie_info['title'],
            'year': movie_info['year'],
            'plot': movie_info['plot'],
            'imdb': movie_info['imdb'],
            'rotten_tomatoes': movie_info['rotten_tomatoes'],
            'trailer': movie_info['trailer'],
            'comment': comment,
            'rating': rating,
            'special': special,
            'poster': movie_info['poster']
        }
    except Exception as e:
        logger.error(f"خطا در get_random_movie: {e}")
        return None

def format_movie_post(movie):
    rating_stars = {5: '⭐️⭐️⭐️⭐️⭐️', 4: '⭐️⭐️⭐️⭐️', 3: '⭐️⭐️⭐️', 2: '⭐️⭐️', 1: '⭐️'}
    special_symbol = ' 👑' if movie.get('special', False) else ''
    post = (
        f"<b>🎬 عنوان فیلم:</b> \n{movie['title']}{special_symbol}\n\n"
        f"<b>📅 سال تولید:</b> {movie['year']}\n\n"
        f"<b>📝 خلاصه داستان:</b> \n{movie['plot']}\n\n"
        f"<b>🌟 امتیاز:</b>\nIMDB: {movie['imdb']}\nRotten Tomatoes: {movie['rotten_tomatoes']}\n\n"
        f"<b>🎞 لینک تریلر:</b> \n{movie['trailer']}\n\n"
        f"<b>🍿 تحلیل ما:</b>\n{movie['comment']}\n\n"
        f"<b>🎯 ارزش دیدن:</b> {rating_stars[movie['rating']]}\n\n"
        f"https://t.me/bestwatch_channel"
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
    await fetch_movies_to_cache()
    await update.message.reply_text(f"✅ لیست فیلم‌ها آپدیت شد! (تعداد: {len(cached_movies)})")

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("❌ فقط ادمین می‌تواند این دستور را اجرا کند!")
        return
        
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
    await fetch_movies_to_cache()
    
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
