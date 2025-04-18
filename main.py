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

async def translate_to_persian(text):
    """ترجمه متن انگلیسی به فارسی با استفاده از OpenAI"""
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
                        "content": "متن انگلیسی را به فارسی روان ترجمه کن."
                    },
                    {
                        "role": "user",
                        "content": text
                    }
                ],
                "temperature": 0.3
            }
            async with session.post(url, json=payload, headers=headers, timeout=20) as response:
                data = await response.json()
                return data['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"خطا در ترجمه: {e}")
        return text  # اگر ترجمه شکست خورد، متن اصلی برگردانده شود

async def get_movie_info(title):
    try:
        async with aiohttp.ClientSession() as session:
            # دریافت اطلاعات از TMDB
            search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
            async with session.get(search_url, timeout=15) as response:
                search_data = await response.json()
                if search_data.get('results'):
                    movie_id = search_data['results'][0]['id']
                    
                    # دریافت جزئیات کامل فیلم
                    detail_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&append_to_response=videos"
                    async with session.get(detail_url, timeout=15) as detail_response:
                        movie_data = await detail_response.json()
                        
                        # دریافت تریلر
                        trailer_key = None
                        if 'videos' in movie_data and movie_data['videos']['results']:
                            for video in movie_data['videos']['results']:
                                if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                    trailer_key = video['key']
                                    break
                        
                        # دریافت امتیاز Rotten Tomatoes از OMDB
                        omdb_url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
                        async with session.get(omdb_url, timeout=15) as omdb_response:
                            omdb_data = await omdb_response.json()
                            ratings = omdb_data.get('Ratings', []) if omdb_data.get('Response') == 'True' else []
                            rt_rating = next((r['Value'] for r in ratings if r['Source'] == 'Rotten Tomatoes'), 'N/A')
                            
                            return {
                                'title': movie_data.get('title', title),
                                'year': movie_data.get('release_date', '')[:4] if movie_data.get('release_date') else 'N/A',
                                'plot': await translate_to_persian(movie_data.get('overview', 'خلاصه‌ای موجود نیست.')),
                                'imdb': str(round(movie_data.get('vote_average', 0), 1)) + '/10',
                                'rotten_tomatoes': rt_rating,
                                'trailer': f"https://www.youtube.com/watch?v={trailer_key}" if trailer_key else 'N/A',
                                'poster': f"https://image.tmdb.org/t/p/w500{movie_data['poster_path']}" if movie_data.get('poster_path') else 'N/A'
                            }
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات فیلم: {e}")
        return None

async def generate_comment(title):
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
                        "content": "تحلیل حرفه‌ای و جذاب درباره فیلم بنویس (حدود 100-120 کلمه). از اصطلاحات سینمایی استفاده کن و نقاط قوت و ضعف اثر را به صورت متعادل بررسی کن."
                    },
                    {
                        "role": "user",
                        "content": f"تحلیل دقیق و جامع درباره فیلم {title}"
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
        return "این فیلم اثری قابل تأمل است که ارزش دیدن دارد. اجرای بازیگران و کارگردانی آن در سطح بالایی قرار دارد."

[بقیه توابع بدون تغییر شامل fetch_movies_to_cache, get_random_movie, format_movie_post, start, fetch_movies, post_now, auto_post, health_check و main]

if __name__ == '__main__':
    asyncio.run(main())
