import os
import logging
import random
import re
from datetime import datetime

import aiohttp
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from aiohttp import web

# --- تنظیمات اولیه ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
ADMIN_ID = os.getenv('ADMIN_ID')
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
PORT = int(os.getenv('PORT', 8080))

# --- کش ---
cached_movies = []
last_fetch_time = None

# --- توابع ---
def clean_text(text):
    return re.sub(r'[^\w\s\-\.\,\!\?\:\(\)\'\"]', '', text)[:300]

async def get_movie_info(title):
    try:
        async with aiohttp.ClientSession() as session:
            omdb_url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            async with session.get(omdb_url, timeout=15) as response:
                omdb_data = await response.json()
                if omdb_data.get('Response') != 'True':
                    return None

                search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
                async with session.get(search_url, timeout=15) as tmdb_response:
                    tmdb_data = await tmdb_response.json()

                    trailer = "N/A"
                    if tmdb_data.get('results'):
                        movie_id = tmdb_data['results'][0]['id']
                        videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
                        async with session.get(videos_url, timeout=15) as videos_response:
                            videos_data = await videos_response.json()
                            for video in videos_data.get('results', []):
                                if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                    trailer = f"https://www.youtube.com/watch?v={video['key']}"
                                    break

                plot = '. '.join(omdb_data.get('Plot', 'No plot available').split('.')[:2])
                imdb_rating = f"{float(omdb_data.get('imdbRating', 0)):.1f}/10"
                rt_rating = next((r['Value'] for r in omdb_data.get('Ratings', []) if r['Source'] == 'Rotten Tomatoes'), 'N/A')

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
    try:
        prompt = f"""تحلیل جامع و حرفه‌ای درباره فیلم {title} به زبان فارسی (حدود 150 کلمه): ..."""
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
            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30) as response:
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
            async with session.get(url, timeout=15) as response:
                data = await response.json()
                if data.get('results'):
                    cached_movies = data['results']
                    last_fetch_time = datetime.now()
                    return True
        return False
    except Exception as e:
        logger.error(f"خطا در آپدیت کش فیلم‌ها: {e}")
        return False

async def get_random_movie():
    global last_fetch_time
    try:
        if not cached_movies or not last_fetch_time or (datetime.now() - last_fetch_time).total_seconds() > 86400:
            await fetch_movies_to_cache()

        movie_data = random.choice(cached_movies)
        title = movie_data.get('title') or movie_data.get('original_title') or 'Unknown'
        movie_info = await get_movie_info(title)
        if not movie_info:
            return None

        comment = await generate_comment(title)
        imdb_score = float(movie_info['imdb'].split('/')[0]) if movie_info['imdb'] != 'N/A' else 0
        rating = min(5, max(1, int(imdb_score // 2)))

        return {
            **movie_info,
            'comment': comment,
            'rating': rating,
            'special': imdb_score >= 8.0
        }

    except Exception as e:
        logger.error(f"خطا در دریافت فیلم تصادفی: {e}")
        return None

def format_movie_post(movie):
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie['special'] else ''
    return f"""
<b>🎬 {movie['title']}{special}</b>
<b>📅 سال:</b> {movie['year']}
<b>📝 خلاصه:</b> {movie['plot']}
<b>🌟 امتیاز:</b> IMDB: {movie['imdb']} | Rotten Tomatoes: {movie['rotten_tomatoes']}
<b>🎞 تریلر:</b> {movie['trailer']}
<b>🍿 تحلیل ما:</b> {movie['comment']}
<b>🎯 ارزش دیدن:</b> {stars}
"""

# --- دستورات تلگرام ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) == ADMIN_ID:
        await update.message.reply_text("🤖 دستورهای ادمین: /fetchmovies - آپدیت لیست | /postnow - ارسال فوری")

async def fetch_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) == ADMIN_ID:
        msg = await update.message.reply_text("در حال آپدیت لیست...")
        if await fetch_movies_to_cache():
            await msg.edit_text("✅ لیست فیلم‌ها آپدیت شد.")
        else:
            await msg.edit_text("❌ خطا در آپدیت لیست فیلم‌ها.")

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) == ADMIN_ID:
        movie = await get_random_movie()
        if movie:
            post = format_movie_post(movie)
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=movie['poster'], caption=post, parse_mode='HTML')
            await update.message.reply_text("✅ پست ارسال شد.")
        else:
            await update.message.reply_text("❌ خطا در دریافت فیلم.")

# --- وب سرور برای Render ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fetchmovies", fetch_movies))
    app.add_handler(CommandHandler("postnow", post_now))

    runner = web.AppRunner(web.Application())
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
