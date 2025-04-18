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

# --- توابع اصلی ---
async def get_movie_info(title):
    """دریافت اطلاعات فیلم با مدیریت خطا"""
    try:
        async with aiohttp.ClientSession() as session:
            # دریافت از OMDB
            omdb_url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            async with session.get(omdb_url, timeout=15) as response:
                omdb_data = await response.json()
                
                if omdb_data.get('Response') != 'True':
                    return None
                    
                # پردازش خلاصه داستان
                plot = '. '.join(omdb_data.get('Plot', 'No plot').split('.')[:2])[:200]
                
                # دریافت تریلر از TMDB
                trailer = await get_trailer(title)
                
                return {
                    'title': omdb_data.get('Title', title),
                    'year': omdb_data.get('Year', 'N/A'),
                    'plot': plot,
                    'imdb': f"{float(omdb_data.get('imdbRating', 0)):.1f}/10",
                    'rotten_tomatoes': next(
                        (r['Value'] for r in omdb_data.get('Ratings', [])
                        if r['Source'] == 'Rotten Tomatoes'), 'N/A'),
                    'trailer': trailer,
                    'poster': omdb_data.get('Poster', 'N/A')
                }
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات: {e}")
        return None

async def get_trailer(title):
    """دریافت تریلر از TMDB"""
    try:
        async with aiohttp.ClientSession() as session:
            search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
            async with session.get(search_url, timeout=15) as response:
                data = await response.json()
                if data.get('results'):
                    movie_id = data['results'][0]['id']
                    videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
                    async with session.get(videos_url, timeout=15) as v_response:
                        videos = await v_response.json()
                        for video in videos.get('results', []):
                            if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                return f"https://youtu.be/{video['key']}"
        return "N/A"
    except Exception as e:
        logger.error(f"خطا در دریافت تریلر: {e}")
        return "N/A"

async def generate_comment(title):
    """تولید تحلیل با OpenAI"""
    try:
        prompt = f"""
        تحلیل دقیق و حرفه‌ای درباره فیلم {title} به زبان فارسی (حدود 150-200 کلمه):
        1. معرفی کلی اثر
        2. بررسی نقاط قوت
        3. بررسی نقاط ضعف
        4. جمع‌بندی و توصیه
        """
        
        async with aiohttp.ClientSession() as session:
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
            
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            ) as response:
                data = await response.json()
                return data['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"خطا در تولید تحلیل: {e}")
        return "تحلیل این فیلم در حال حاضر موجود نیست."

[بقیه توابع مانند fetch_movies_to_cache, get_random_movie, format_movie_post و دستورات با تغییرات مشابه]

async def main():
    # راه‌اندازی با timeout بیشتر
    app = Application.builder() \
        .token(TELEGRAM_TOKEN) \
        .read_timeout(30) \
        .write_timeout(30) \
        .build()
    
    # ثبت دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fetchmovies", fetch_movies))
    app.add_handler(CommandHandler("postnow", post_now))
    
    # راه‌اندازی سرور سلامت
    runner = web.AppRunner(web.Application(
        routes=[web.get('/health', lambda _: web.Response(text="OK"))]
    ))
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    
    # شروع بات
    await app.initialize()
    await app.start()
    logger.info("ربات با موفقیت راه‌اندازی شد")
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
