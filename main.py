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
            omdb_url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            async with session.get(omdb_url) as response:
                omdb_data = await response.json()
                
                if omdb_data.get('Response') != 'True':
                    return None
                
                search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
                async with session.get(search_url) as tmdb_response:
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
                    
                    plot = '. '.join(omdb_data.get('Plot', 'No plot available').split('.')[:2])
                    
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
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات فیلم: {e}")
        return None

async def generate_comment(title):
    """تولید تحلیل حرفه‌ای با OpenAI"""
    try:
        prompt = f"""
        تحلیل جامع و حرفه‌ای درباره فیلم {title} به زبان فارسی (حدود 150 کلمه):
        1. معرفی کلی فیلم
        2. نقاط قوت اصلی
        3. نقاط ضعف
        4. جمع‌بندی و توصیه
        لطفاً تحلیل را با لحن حرفه‌ای و جذاب بنویسید.
        """
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY.strip()}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 300
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                data = await response.json()
                return data['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"خطا در تولید تحلیل: {e}")
        return "تحلیل این فیلم در حال حاضر موجود نیست."

async def fetch_movies_to_cache():
    global cached_movies, last_fetch_time
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page=1"
            async with session.get(url) as response:
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
        
        if imdb_score >= 9.0:
            rating = 5
        elif 8.0 <= imdb_score < 9.0:
            rating = 4
        elif 6.5 <= imdb_score < 8.0:
            rating = 3
        elif 5.0 <= imdb_score < 6.5:
            rating = 2
        else:
            rating = 1
        
        return {
            **movie_info,
            'comment': comment,
            'rating': rating,
            'special': imdb_score >= 9.5
        }
    except Exception as e:
        logger.error(f"خطا در انتخاب فیلم: {e}")
        return None

def format_movie_post(movie):
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie['special'] else ''
    channel_link = '[\\@BestWatch](https://t.me/bestwatch_channel)'
    
    return f"""
*🎬 {movie['title']}{special}*
*📅 سال:* {movie['year']}
*📝 خلاصه:* {movie['plot']}
*🌟 امتیاز:* IMDB: {movie['imdb']} | Rotten Tomatoes: {movie['rotten_tomatoes']}
*🎞 تریلر:* {movie['trailer']}
*🍿 تحلیل ما:* {movie['comment']}
*🎯 ارزش دیدن:* {stars}

*کانال سینمایی ما:* {channel_link}
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) == ADMIN_ID:
        await update.message.reply_text("""
🤖 دستورات ادمین:
/fetchmovies - آپدیت لیست فیلم‌ها
/postnow - ارسال پست فوری
""")

async def fetch_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) == ADMIN_ID:
        msg = await update.message.reply_text("در حال آپدیت لیست...")
        if await fetch_movies_to_cache():
            await msg.edit_text(f"✅ لیست آپدیت شد! ({len(cached_movies)} فیلم)")
        else:
            await msg.edit_text("❌ خطا در آپدیت لیست")

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) == ADMIN_ID:
        msg = await update.message.reply_text("در حال آماده‌سازی پست...")
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
                await msg.edit_text(f"✅ پست {movie['title']} ارسال شد")
            except Exception as e:
                logger.error(f"خطا در ارسال پست: {e}")
                await msg.edit_text("❌ خطا در ارسال پست")
        else:
            await msg.edit_text("❌ خطا در یافتن فیلم")

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
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
        except Exception as e:
            logger.error(f"خطا در ارسال خودکار پست: {e}")

async def health_check(request):
    return web.Response(text="OK")

async def main():
    # راه‌اندازی اولیه
    if not await fetch_movies_to_cache():
        logger.error("❌ خطا در دریافت اولیه لیست فیلم‌ها")
    
    # تنظیمات Application
    app = Application.builder() \
        .token(TELEGRAM_TOKEN) \
        .build()
    
    # ثبت دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fetchmovies", fetch_movies))
    app.add_handler(CommandHandler("postnow", post_now))
    
    # تنظیم JobQueue
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(auto_post, interval=600, first=10)
    
    # راه‌اندازی سرور سلامت
    runner = web.AppRunner(web.Application())
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    # شروع بات
    await app.initialize()
    await app.start()
    logger.info("🤖 ربات با موفقیت راه‌اندازی شد")
    
    # اجرای نامحدود
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())
