import asyncio
import logging
import os
import random
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
import genai
import httpx
import telegram
from dotenv import load_dotenv
from openai import AsyncOpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# تنظیم لاگ‌گذاری
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# بارگذاری متغیرهای محیطی
load_dotenv()

# ثابت‌ها
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# تنظیم APIها
genai.configure(api_key=GOOGLE_API_KEY)
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# دیکشنری ترجمه ژانرها
GENRE_TRANSLATIONS = {
    "Action": "اکشن",
    "Adventure": "ماجراجویی",
    "Animation": "انیمیشن",
    "Comedy": "کمدی",
    "Crime": "جنایی",
    "Documentary": "مستند",
    "Drama": "درام",
    "Family": "خانوادگی",
    "Fantasy": "فانتزی",
    "History": "تاریخی",
    "Horror": "ترسناک",
    "Music": "موسیقی",
    "Mystery": "رازآلود",
    "Romance": "عاشقانه",
    "Science Fiction": "علمی-تخیلی",
    "Thriller": "هیجان‌انگیز",
    "War": "جنگی",
    "Western": "وسترن"
}

# فال‌بک نظرات
FALLBACK_COMMENTS = {
    "انیمیشن": [
        "این انیمیشن با جلوه‌های بصری خیره‌کننده و داستانی پرمغز، تجربه‌ای به‌یادماندنی برای تمام سنین خلق می‌کند. شخصیت‌پردازی عمیق و موسیقی متن دل‌انگیز، مخاطب را به دنیایی خیالی می‌برد. در نهایت، پیامی الهام‌بخش از امید و شجاعت ارائه می‌دهد.",
        "داستانی سرشار از ماجرا و طنز که قلب هر بیننده‌ای را تسخیر می‌کند. انیمیشن‌های رنگارنگ و دیالوگ‌های هوشمندانه، لحظه‌هایی پر از خنده و تأمل می‌سازند. اثری که درس‌های زندگی را با ظرافت منتقل می‌کند."
    ],
    "default": [
        "این فیلم با روایتی گیرا و بازی‌های درخشان، بیننده را به سفری احساسی دعوت می‌کند. کارگردانی هنرمندانه و فیلم‌برداری نفس‌گیر، داستانی عمیق را به تصویر می‌کشد. اثری که تا مدت‌ها در ذهن مخاطب باقی می‌ماند.",
        "ترکیبی استادانه از هیجان و احساس که با پیچش‌های داستانی غافلگیرکننده همراه است. شخصیت‌های چندلایه و دیالوگ‌های تأثیرگذار، تجربه‌ای سینمایی خلق می‌کنند. فیلمی که ارزش تماشای چندباره دارد."
    ]
}

# متغیرهای جهانی
posted_movies: List[str] = []
previous_comments: List[str] = []
api_availability = {
    "tmdb": True,
    "omdb": True,
    "gemini": True,
    "groq": True,
    "deepseek": True,
    "openai": True
}
api_errors = {"tmdb": 0, "omdb": 0}
min_chars, max_chars = 300, 500

# توابع کمکی
def is_farsi(text: str) -> bool:
    farsi_chars = r'[\u0600-\u06FF]'
    return bool(re.search(farsi_chars, text))

def get_fallback_by_genre(comments: Dict[str, List[str]], genres: Optional[List[str]]) -> str:
    if genres and "انیمیشن" in genres:
        return random.choice(comments["انیمیشن"])
    return random.choice(comments["default"])

def limit_text_length(text: str, min_chars: int = 300, max_chars: int = 500) -> str:
    text = text.strip()
    text = re.sub(r'\s+', ' ', text.replace('\u200C', ' ').replace('\u200F', ' '))
    if len(text) > max_chars:
        shortened = text[:max_chars]
        last_period = shortened.rfind('.')
        if last_period > min_chars:
            text = shortened[:last_period + 1]
        else:
            text = shortened[:max_chars].strip() + '...'
    if len(text) < min_chars:
        logger.warning(f"متن خیلی کوتاه است: {len(text)} کاراکتر")
    return text

async def make_api_request(url: str, retries: int = 3) -> Optional[Dict]:
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"خطای HTTP در {url}: {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"خطا در درخواست به {url}: {str(e)}")
            return None
    return None

async def post_api_request(url: str, data: Dict, headers: Dict, retries: int = 3) -> Optional[Dict]:
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=data, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"خطای HTTP در {url}: {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"خطا در درخواست POST به {url}: {str(e)}")
            return None
    return None

async def get_imdb_score_tmdb(title: str, genres: Optional[List[str]] = None) -> Optional[str]:
    logger.info(f"دریافت اطلاعات TMDB برای: {title}")
    encoded_title = urllib.parse.quote(title)
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=en-US"
    data = await make_api_request(url)
    if not data or not data.get('results'):
        logger.warning(f"TMDB هیچ نتیجه‌ای برای {title} نداد")
        api_errors['tmdb'] += 1
        return None
    movie = data['results'][0]
    imdb_score = movie.get('vote_average', 0)
    
    is_animation = False
    if genres:
        is_animation = 'انیمیشن' in genres
    else:
        details_url = f"https://api.themoviedb.org/3/movie/{movie.get('id')}?api_key={TMDB_API_KEY}&language=en-US"
        details_data = await make_api_request(details_url)
        genres = [GENRE_TRANSLATIONS.get(g['name'], 'سایر') for g in details_data.get('genres', [])]
        is_animation = 'انیمیشن' in genres
    
    min_score = 8.0 if is_animation else 6.0
    if imdb_score < min_score:
        logger.warning(f"فیلم {title} امتیاز {imdb_score} دارد، رد شد (حداقل {min_score} لازم است)")
        return None
    api_errors['tmdb'] = 0
    return f"{float(imdb_score):.1f}/10"

async def get_imdb_score_omdb(title: str, genres: Optional[List[str]] = None) -> Optional[str]:
    logger.info(f"دریافت اطلاعات OMDb برای: {title}")
    encoded_title = urllib.parse.quote(title)
    url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_title}&type=movie"
    data = await make_api_request(url)
    if not data or data.get('Response') == 'False':
        logger.warning(f"OMDb هیچ نتیجه‌ای برای {title} نداد: {data.get('Error')}")
        api_errors['omdb'] += 1
        return None
    imdb_score = data.get('imdbRating', '0')
    
    is_animation = False
    if genres:
        is_animation = 'انیمیشن' in genres
    else:
        genres = data.get('Genre', '').split(', ')
        genres = [GENRE_TRANSLATIONS.get(g.strip(), 'سایر') for g in genres]
        is_animation = 'انیمیشن' in genres
    
    min_score = 8.0 if is_animation else 6.0
    if float(imdb_score) < min_score:
        logger.warning(f"فیلم {title} امتیاز {imdb_score} دارد، رد شد (حداقل {min_score} لازم است)")
        return None
    api_errors['omdb'] = 0
    return f"{float(imdb_score):.1f}/10"

async def generate_comment(genres: Optional[List[str]] = None) -> str:
    logger.info("تولید تحلیل...")

    # 1. Gemini
    if api_availability['gemini']:
        logger.info("تلاش با Gemini")
        try:
            async with asyncio.timeout(10):
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = "یک تحلیل کوتاه و جذاب به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، بین 300 تا 500 کاراکتر. لحن حرفه‌ای و سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد. فقط به فارسی بنویس و از کلمات انگلیسی استفاده نکن."
                response = await model.generate_content_async(prompt)
                text = response.text.strip()
                text = limit_text_length(text)
                logger.info(f"تحلیل Gemini: {text}")
                logger.info(f"طول متن: {len(text)}, فارسی: {is_farsi(text)}")
                if min_chars <= len(text) <= max_chars and is_farsi(text):
                    previous_comments.append(text)
                    if len(previous_comments) > 10:
                        previous_comments.pop(0)
                    logger.info("تحلیل Gemini با موفقیت دریافت شد")
                    return text
                logger.warning(f"تحلیل Gemini نامعتبر: طول={len(text)}, فارسی={is_farsi(text)}")
        except genai.exceptions.ResourceExhausted:
            logger.error("خطا: توکن Gemini تمام شده است")
            api_availability['gemini'] = False
            await send_admin_alert(None, "❌ توکن Gemini تمام شده است.")
        except Exception as e:
            logger.error(f"خطا در Gemini API: {str(e)}")
            api_availability['gemini'] = False
            await send_admin_alert(None, f"❌ خطا در Gemini: {str(e)}.")

    # 2. Groq
    if api_availability['groq']:
        logger.info("تلاش با Groq")
        try:
            async with asyncio.timeout(10):
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": "mistral-saba-24b",
                    "messages": [
                        {"role": "system", "content": "You are a professional film critic writing in Persian."},
                        {"role": "user", "content": "یک تحلیل کوتاه و جذاب به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، بین 300 تا 500 کاراکتر. لحن حرفه‌ای و سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد. فقط به فارسی بنویس و از کلمات انگلیسی استفاده نکن."}
                    ],
                    "max_tokens": 200,
                    "temperature": 0.9
                }
                response = await post_api_request(url, data, headers, retries=3)
                if response and response.get('choices'):
                    text = response['choices'][0]['message']['content'].strip()
                    text = limit_text_length(text)
                    if min_chars <= len(text) <= max_chars and is_farsi(text):
                        previous_comments.append(text)
                        if len(previous_comments) > 10:
                            previous_comments.pop(0)
                        logger.info("تحلیل Groq با موفقیت دریافت شد")
                        return text
                    logger.warning(f"تحلیل Groq نامعتبر: طول={len(text)}, فارسی={is_farsi(text)}")
                else:
                    logger.warning(f"پاسخ Groq خالی یا نامعتبر: {response}")
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.error(f"خطای اتصال Groq: {str(e)}")
            api_availability['groq'] = False
            await send_admin_alert(None, f"❌ مشکل اتصال به Groq: {str(e)}.")
        except Exception as e:
            logger.error(f"خطا در Groq API: {str(e)}")
            api_availability['groq'] = False
            await send_admin_alert(None, f"❌ خطا در Groq: {str(e)}.")

    # 3. DeepSeek
    if api_availability['deepseek']:
        logger.info("تلاش با DeepSeek")
        try:
            async with asyncio.timeout(10):
                url = "https://api.deepseek.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "You are a professional film critic writing in Persian."},
                        {"role": "user", "content": "یک تحلیل کوتاه و جذاب به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، بین 300 تا 500 کاراکتر. لحن حرفه‌ای و سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد. فقط به فارسی بنویس و از کلمات انگلیسی استفاده نکن."}
                    ],
                    "max_tokens": 200,
                    "temperature": 0.9
                }
                response = await post_api_request(url, data, headers, retries=3)
                if response and response.get('choices'):
                    text = response['choices'][0]['message']['content'].strip()
                    text = limit_text_length(text)
                    if min_chars <= len(text) <= max_chars and is_farsi(text):
                        previous_comments.append(text)
                        if len(previous_comments) > 10:
                            previous_comments.pop(0)
                        logger.info("تحلیل DeepSeek با موفقیت دریافت شد")
                        return text
                    logger.warning(f"تحلیل DeepSeek نامعتبر: طول={len(text)}, فارسی={is_farsi(text)}")
                else:
                    logger.warning(f"پاسخ DeepSeek خالی یا نامعتبر: {response}")
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.error(f"خطای اتصال DeepSeek: {str(e)}")
            api_availability['deepseek'] = False
            await send_admin_alert(None, f"❌ مشکل اتصال به DeepSeek: {str(e)}.")
        except Exception as e:
            logger.error(f"خطا در DeepSeek API: {str(e)}")
            api_availability['deepseek'] = False
            await send_admin_alert(None, f"❌ خطا در DeepSeek: {str(e)}.")

    # 4. Open AI
    if api_availability['openai']:
        logger.info("تلاش با Open AI")
        try:
            async with asyncio.timeout(10):
                response = await client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a professional film critic writing in Persian."},
                        {"role": "user", "content": "یک تحلیل کوتاه و جذاب به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، بین 300 تا 500 کاراکتر. لحن حرفه‌ای و سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد. فقط به فارسی بنویس و از کلمات انگلیسی استفاده نکن."}
                    ],
                    max_tokens=200,
                    temperature=0.9
                )
                text = response.choices[0].message.content.strip()
                text = limit_text_length(text)
                if min_chars <= len(text) <= max_chars and is_farsi(text):
                    previous_comments.append(text)
                    if len(previous_comments) > 10:
                        previous_comments.pop(0)
                    logger.info("تحلیل Open AI با موفقیت دریافت شد")
                    return text
                logger.warning(f"تحلیل Open AI نامعتبر: طول={len(text)}, فارسی={is_farsi(text)}")
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.error(f"خطای اتصال Open AI: {str(e)}")
            api_availability['openai'] = False
            await send_admin_alert(None, f"❌ مشکل اتصال به Open AI: {str(e)}.")
        except Exception as e:
            logger.error(f"خطا در Open AI API: {str(e)}")
            api_availability['openai'] = False
            await send_admin_alert(None, f"❌ خطا در Open AI: {str(e)}.")

    # 5. فال‌بک
    logger.warning("هیچ تحلیلگری در دسترس نیست، استفاده از فال‌بک")
    comment = get_fallback_by_genre(FALLBACK_COMMENTS, genres)
    comment = limit_text_length(comment)
    previous_comments.append(comment)
    if len(previous_comments) > 10:
        previous_comments.pop(0)
    return comment

async def get_movie_info(title: str) -> Optional[Dict]:
    logger.info(f"دریافت اطلاعات برای فیلم: {title}")
    
    genres = None
    score = None
    
    if api_availability['tmdb'] and api_errors['tmdb'] < 3:
        logger.info(f"تلاش با TMDB برای {title}")
        score = await get_imdb_score_tmdb(title)
        if score:
            details_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={urllib.parse.quote(title)}&language=fa-IR"
            data = await make_api_request(details_url)
            if data and data.get('results'):
                movie = data['results'][0]
                genres = [GENRE_TRANSLATIONS.get(g['name'], 'سایر') for g in movie.get('genres', [])]
    
    if not score and api_availability['omdb'] and api_errors['omdb'] < 3:
        logger.info(f"تلاش با OMDb برای {title}")
        score = await get_imdb_score_omdb(title)
        if score and not genres:
            url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={urllib.parse.quote(title)}&type=movie"
            data = await make_api_request(url)
            if data and data.get('Genre'):
                genres = [GENRE_TRANSLATIONS.get(g.strip(), 'سایر') for g in data['Genre'].split(', ')]
    
    if not score:
        logger.error(f"هیچ امتیازی برای {title} یافت نشد")
        return None
    
    if not genres:
        genres = ['سایر']
    
    return {
        "title": title,
        "genres": genres,
        "score": score
    }

async def select_random_movie() -> Optional[Dict]:
    logger.info("انتخاب فیلم تصادفی...")
    url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=fa-IR&page=1"
    data = await make_api_request(url)
    
    if not data or not data.get('results'):
        logger.error("دریافت فیلم‌های محبوب از TMDB ناموفق بود")
        return None
    
    movies = data['results']
    max_attempts = 10
    
    for attempt in range(max_attempts):
        movie = random.choice(movies)
        title = movie.get('title')
        if title in posted_movies:
            continue
        
        movie_info = await get_movie_info(title)
        if movie_info:
            logger.info(f"فیلم انتخاب شد: {title} (تلاش {attempt + 1})")
            posted_movies.append(title)
            if len(posted_movies) > 100:
                posted_movies.pop(0)
            return movie_info
    
    logger.error("هیچ فیلم مناسبی پیدا نشد")
    return None

async def send_admin_alert(update: Optional[Update], message: str):
    if not ADMIN_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID تنظیم نشده است")
        return
    
    try:
        app = update.application if update else Application.builder().token(BOT_TOKEN).build()
        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=message)
    except Exception as e:
        logger.error(f"خطا در ارسال هشدار به ادمین: {str(e)}")

async def run_tests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    results = []

    # تست TMDB
    tmdb_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=fa-IR&page=1"
    tmdb_data = await make_api_request(tmdb_url)
    tmdb_status = "✅ TMDB اوکی" if tmdb_data and tmdb_data.get('results') else f"❌ TMDB خطا: {tmdb_data}"
    results.append(tmdb_status)

    # تست OMDb
    omdb_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t=Inception&type=movie"
    omdb_data = await make_api_request(omdb_url)
    omdb_status = "✅ OMDb اوکی" if omdb_data and omdb_data.get('Response') == 'True' else f"❌ OMDb خطا: {omdb_data.get('Error')}"
    results.append(omdb_status)

    # تست JobQueue
    job_queue = context.job_queue
    results.append("✅ JobQueue فعال" if job_queue else "❌ JobQueue غیرفعال")

    # تست Gemini
    if api_availability['gemini']:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = "تست: یک جمله به فارسی بنویس."
            response = await model.generate_content_async(prompt)
            text = response.text.strip()
            gemini_status = "✅ Gemini اوکی" if text and is_farsi(text) else "❌ Gemini خطا: پاسخ نامعتبر"
            results.append(gemini_status)
        except Exception as e:
            logger.error(f"خطا در تست Gemini: {str(e)}")
            api_availability['gemini'] = False
            results.append(f"❌ Gemini خطا: {str(e)}")

    # تست Groq
    if api_availability['groq']:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "mistral-saba-24b",
                "messages": [
                    {"role": "system", "content": "Write in Persian."},
                    {"role": "user", "content": "تست: یک جمله به فارسی بنویس."}
                ],
                "max_tokens": 50,
                "temperature": 0.9
            }
            response = await post_api_request(url, data, headers, retries=3)
            text = response['choices'][0]['message']['content'].strip() if response and response.get('choices') else ""
            groq_status = "✅ Groq اوکی" if text and is_farsi(text) else f"❌ Groq خطا: پاسخ نامعتبر - متن دریافتی: {text}"
            results.append(groq_status)
        except Exception as e:
            logger.error(f"خطا در تست Groq: {str(e)}")
            api_availability['groq'] = False
            results.append(f"❌ Groq خطا: {str(e)}")

    # تست DeepSeek
    if api_availability['deepseek']:
        try:
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "Write in Persian."},
                    {"role": "user", "content": "تست: یک جمله به فارسی بنویس."}
                ],
                "max_tokens": 50,
                "temperature": 0.9
            }
            response = await post_api_request(url, data, headers, retries=3)
            text = response['choices'][0]['message']['content'].strip() if response and response.get('choices') else ""
            deepseek_status = "✅ DeepSeek اوکی" if text and is_farsi(text) else f"❌ DeepSeek خطا: پاسخ نامعتبر - متن دریافتی: {text}"
            results.append(deepseek_status)
        except Exception as e:
            logger.error(f"خطا در تست DeepSeek: {str(e)}")
            api_availability['deepseek'] = False
            results.append(f"❌ DeepSeek خطا: {str(e)}")

    # تست Open AI
    if api_availability['openai']:
        try:
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Write in Persian."},
                    {"role": "user", "content": "تست: یک جمله به فارسی بنویس."}
                ],
                max_tokens=50,
                temperature=0.9
            )
            text = response.choices[0].message.content.strip()
            openai_status = "✅ Open AI اوکی" if text and is_farsi(text) else "❌ Open AI خطا: پاسخ نامعتبر"
            results.append(openai_status)
        except Exception as e:
            logger.error(f"خطا در تست Open AI: {str(e)}")
            api_availability['openai'] = False
            results.append(f"❌ Open AI خطا: {str(e)}")

    await update.message.reply_text("\n".join(results))

async def post_movie(context: ContextTypes.DEFAULT_TYPE) -> None:
    movie_info = await select_random_movie()
    if not movie_info:
        logger.error("هیچ فیلمی برای ارسال انتخاب نشد")
        await send_admin_alert(None, "❌ هیچ فیلمی برای ارسال انتخاب نشد!")
        return
    
    title = movie_info['title']
    genres = movie_info['genres']
    score = movie_info['score']
    
    comment = await generate_comment(genres)
    
    post_text = f"🎬 *{title}*\n\n"
    post_text += f"📖 ژانر: {', '.join(genres)}\n"
    post_text += f"⭐ امتیاز IMDb: {score}\n\n"
    post_text += f"💬 *حرف ما*: {comment}"
    
    try:
        message = await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=post_text,
            parse_mode=telegram.constants.ParseMode.MARKDOWN
        )
        logger.info(f"ارسال پست برای: {title}")
        
        posted_movies.append(str(message.message_id))
        logger.info(f"لیست فیلم‌های ارسال‌شده ذخیره شد: {len(posted_movies)} فیلم")
        logger.info(f"فیلم‌های ارسال‌شده: {posted_movies[-2:]}")
    except telegram.error.TimedOut:
        logger.error("خطای تایم‌اوت هنگام ارسال پست")
        await send_admin_alert(None, "❌ خطای تایم‌اوت هنگام ارسال پست!")
    except Exception as e:
        logger.error(f"خطا در ارسال پست: {str(e)}")
        await send_admin_alert(None, f"❌ خطا در ارسال پست: {str(e)}.")

async def immediate_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await post_movie(context)
    await update.message.reply_text("✅ پست فوری ارسال شد!")

async def error_handler(update: Optional[Update], context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"خطا رخ داد: {context.error}")
    await send_admin_alert(update, f"❌ خطای بات: {context.error}")

def main() -> None:
    # غیرفعال کردن موقت DeepSeek به دلیل خطای 402
    # api_availability['deepseek'] = False  # این خط رو اگه نمی‌خوای DeepSeek کار کنه، از کامنت دربیار

    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("test", run_tests))
    application.add_handler(CommandHandler("post", immediate_post))
    application.add_error_handler(error_handler)
    
    job_queue = application.job_queue
    job_queue.run_repeating(post_movie, interval=24*60*60, first=10)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
