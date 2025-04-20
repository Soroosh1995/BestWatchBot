import asyncio
import aiohttp
import random
import urllib.parse
import logging
import json
import re
import os
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import google.generativeai as genai
import openai
from typing import Dict, List, Optional
from collections import deque
import httpx

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# متغیرهای محیطی
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# تنظیمات Open AI
openai.api_key = OPENAI_API_KEY
client = openai.AsyncOpenAI()

# تنظیمات Google Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# دیکشنری برای ترجمه ژانرها
GENRE_TRANSLATIONS = {
    'Action': 'اکشن',
    'Adventure': 'ماجراجویی',
    'Animation': 'انیمیشن',
    'Comedy': 'کمدی',
    'Crime': 'جنایی',
    'Documentary': 'مستند',
    'Drama': 'درام',
    'Family': 'خانوادگی',
    'Fantasy': 'فانتزی',
    'History': 'تاریخی',
    'Horror': 'ترسناک',
    'Music': 'موسیقی',
    'Mystery': 'رازآلود',
    'Romance': 'عاشقانه',
    'Science Fiction': 'علمی-تخیلی',
    'Thriller': 'هیجان‌انگیز',
    'War': 'جنگی',
    'Western': 'وسترن'
}

# متغیرهای سراسری
api_errors: Dict[str, int] = {'tmdb': 0, 'omdb': 0, 'groq': 0, 'gemini': 0, 'deepseek': 0, 'openai': 0}
api_availability: Dict[str, bool] = {'tmdb': True, 'omdb': True, 'groq': True, 'gemini': True, 'deepseek': True, 'openai': True}
previous_comments: List[str] = deque(maxlen=10)
posted_movies: List[str] = []
min_chars = 300
max_chars = 500

# فال‌بک‌ها برای نظرات
FALLBACK_COMMENTS = {
    'اکشن': 'این فیلم با صحنه‌های نفس‌گیر و هیجان‌انگیز خود، مخاطب را به سفری پر از آدرنالین می‌برد. کارگردانی پویا و جلوه‌های ویژه خیره‌کننده، تجربه‌ای فراموش‌نشدنی خلق می‌کنند. داستانی پرشتاب که تا آخرین لحظه شما را میخکوب نگه می‌دارد.',
    'انیمیشن': 'جهانی رنگارنگ و خلاقانه که قلب و ذهن هر بیننده‌ای را تسخیر می‌کند. داستان‌گویی عمیق و شخصیت‌پردازی جذاب، این اثر را برای تمام سنین دیدنی می‌کند. پیامی الهام‌بخش که با تصاویری شگفت‌انگیز همراه شده است.',
    'کمدی': 'خنده‌هایی از ته دل با موقعیت‌های طنزآمیز و دیالوگ‌های هوشمندانه. بازیگران با شیمی فوق‌العاده، لحظاتی شاد و به‌یادماندنی خلق می‌کنند. فیلمی که روحیه‌تان را تازه می‌کند و لبخند را به لبانتان می‌آورد.',
    'درام': 'روایتی عمیق و تأثیرگذار که احساسات را به چالش می‌کشد. بازی‌های درخشان و کارگردانی حساس، داستانی انسانی را به تصویر می‌کشند. فیلمی که تا مدت‌ها در ذهن و قلب شما باقی می‌ماند.',
    'سایر': 'داستانی منحصربه‌فرد که با روایتی گیرا شما را مجذوب می‌کند. ترکیبی از احساسات و خلاقیت که تجربه‌ای متفاوت ارائه می‌دهد. اثری که شایسته تماشا و تأمل است.'
}

# توابع کمکی
def is_farsi(text: str) -> bool:
    farsi_chars = r'[\u0600-\u06FF]'
    return bool(re.search(farsi_chars, text))

async def make_api_request(url: str, retries: int = 3) -> Optional[Dict]:
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"خطای HTTP در {url}: {e}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"خطا در درخواست به {url}: {e}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
    return None

async def post_api_request(url: str, data: Dict, headers: Dict, retries: int = 3) -> Optional[Dict]:
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=data, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"خطای HTTP در POST به {url}: {e}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"خطا در POST به {url}: {e}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
    return None

def limit_text_length(text, min_chars=300, max_chars=500):
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

def get_fallback_by_genre(fallbacks: Dict[str, str], genres: List[str]) -> str:
    for genre in genres:
        if genre in fallbacks:
            return fallbacks[genre]
    return fallbacks['سایر']

async def send_admin_alert(update: Update, message: str):
    if ADMIN_CHAT_ID:
        try:
            app = update.application if update else Application.builder().token(BOT_TOKEN).build()
            await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=message)
        except Exception as e:
            logger.error(f"خطا در ارسال هشدار به ادمین: {e}")

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

async def get_movie_info(title: str, genres: Optional[List[str]] = None) -> Optional[Dict]:
    score = None
    if api_availability['tmdb'] and api_errors['tmdb'] < 3:
        logger.info(f"تلاش با TMDB برای {title}")
        score = await get_imdb_score_tmdb(title, genres)
    if not score and api_availability['omdb'] and api_errors['omdb'] < 3:
        logger.info(f"تلاش با OMDb برای {title}")
        score = await get_imdb_score_omdb(title, genres)
    if not score:
        logger.warning(f"هیچ اطلاعاتی برای {title} پیدا نشد")
        return None
    
    if not genres:
        url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={urllib.parse.quote(title)}&type=movie"
        data = await make_api_request(url)
        if data and data.get('Response') == 'True':
            genres = data.get('Genre', '').split(', ')
            genres = [GENRE_TRANSLATIONS.get(g.strip(), 'سایر') for g in genres]
    
    return {'title': title, 'score': score, 'genres': genres}

async def generate_comment(genres: List[str]) -> str:
    logger.info("تولید تحلیل...")

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
        except google_exceptions.ResourceExhausted:
            logger.error("خطا: توکن Gemini تمام شده است")
            api_availability['gemini'] = False
            await send_admin_alert(None, "❌ توکن Gemini تمام شده است.")
        except Exception as e:
            logger.error(f"خطا در Gemini API: {str(e)}")
            api_availability['gemini'] = False
            await send_admin_alert(None, f"❌ خطا در Gemini: {str(e)}.")

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

    logger.warning("هیچ تحلیلگری در دسترس نیست، استفاده از فال‌بک")
    comment = get_fallback_by_genre(FALLBACK_COMMENTS, genres)
    comment = limit_text_length(comment)
    previous_comments.append(comment)
    if len(previous_comments) > 10:
        previous_comments.pop(0)
    return comment

async def select_random_movie() -> Optional[Dict]:
    logger.info("انتخاب فیلم تصادفی...")
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            page = random.randint(1, 100)
            url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=fa-IR&page={page}"
            data = await make_api_request(url)
            if not data or not data.get('results'):
                logger.warning(f"TMDB هیچ نتیجه‌ای برای صفحه {page} نداد")
                continue
            movies = data['results']
            movie = random.choice(movies)
            title = movie.get('title')
            if title in posted_movies:
                logger.info(f"فیلم {title} قبلاً ارسال شده، تلاش دوباره...")
                continue
            genres = [GENRE_TRANSLATIONS.get(g['name'], 'سایر') for g in movie.get('genres', [])]
            movie_info = await get_movie_info(title, genres)
            if movie_info:
                logger.info(f"فیلم انتخاب شد: {title} (تلاش {attempt + 1})")
                return movie_info
            logger.info(f"فیلم {title} رد شد، تلاش دوباره...")
        except Exception as e:
            logger.error(f"خطا در انتخاب فیلم: {e}")
            if attempt == max_attempts - 1:
                await send_admin_alert(None, f"❌ خطا در انتخاب فیلم پس از {max_attempts} تلاش: {str(e)}.")
    logger.error("هیچ فیلمی انتخاب نشد")
    return None

async def save_posted_movies():
    try:
        with open('posted_movies.json', 'w', encoding='utf-8') as f:
            json.dump(posted_movies, f, ensure_ascii=False, indent=2)
        logger.info(f"لیست فیلم‌های ارسال‌شده ذخیره شد: {len(posted_movies)} فیلم")
    except Exception as e:
        logger.error(f"خطا در ذخیره لیست فیلم‌های ارسال‌شده: {e}")

async def load_posted_movies():
    global posted_movies
    try:
        with open('posted_movies.json', 'r', encoding='utf-8') as f:
            posted_movies = json.load(f)
        logger.info(f"لیست فیلم‌های ارسال‌شده بارگذاری شد: {len(posted_movies)} فیلم")
    except FileNotFoundError:
        logger.info("فایل posted_movies.json یافت نشد، شروع با لیست خالی")
        posted_movies = []
    except Exception as e:
        logger.error(f"خطا در بارگذاری لیست فیلم‌های ارسال‌شده: {e}")
        posted_movies = []

async def post_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("ارسال پست جدید...")
    movie = await select_random_movie()
    if not movie:
        await send_admin_alert(update, "❌ هیچ فیلمی برای ارسال یافت نشد!")
        return
    
    title = movie['title']
    score = movie['score']
    genres = movie['genres']
    
    comment = await generate_comment(genres)
    message = f"🎬 *{title}*\n\n📊 امتیاز: {score}\n\n💬 *حرف ما*: {comment}"
    
    try:
        sent_message = await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=message,
            parse_mode='Markdown'
        )
        posted_movies.append(title)
        await save_posted_movies()
        logger.info(f"ارسال پست برای: {title}")
        
        await asyncio.sleep(60)
        new_comment = await generate_comment(genres)
        updated_message = f"🎬 *{title}*\n\n📊 امتیاز: {score}\n\n💬 *حرف ما*: {new_comment}"
        await context.bot.edit_message_text(
            chat_id=CHANNEL_ID,
            message_id=sent_message.message_id,
            text=updated_message,
            parse_mode='Markdown'
        )
        logger.info(f"به‌روزرسانی پست برای: {title}")
    except Exception as e:
        logger.error(f"خطا در ارسال یا به‌روزرسانی پست: {e}")
        await send_admin_alert(update, f"❌ خطا در ارسال پست برای {title}: {str(e)}.")

async def run_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = []

    tmdb_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=fa-IR&page=1"
    tmdb_data = await make_api_request(tmdb_url)
    tmdb_status = "✅ TMDB اوکی" if tmdb_data and tmdb_data.get('results') else f"❌ TMDB خطا: {tmdb_data}"
    results.append(tmdb_status)

    omdb_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t=Inception&type=movie"
    omdb_data = await make_api_request(omdb_url)
    omdb_status = "✅ OMDb اوکی" if omdb_data and omdb_data.get('Response') == 'True' else f"❌ OMDb خطا: {omdb_data.get('Error')}"
    results.append(omdb_status)

    job_queue = context.job_queue
    results.append("✅ JobQueue فعال" if job_queue else "❌ JobQueue غیرفعال")

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

async def schedule_posts(context: ContextTypes.DEFAULT_TYPE):
    while True:
        try:
            await post_movie(None, context)
        except Exception as e:
            logger.error(f"خطا در زمان‌بندی پست: {e}")
            await send_admin_alert(None, f"❌ خطا در زمان‌بندی پست: {str(e)}.")
        await asyncio.sleep(4 * 60 * 60)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بات فیلم شروع شد! برای تست وضعیت از /test استفاده کنید.")

async def main():
    await load_posted_movies()
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", run_tests))
    
    app.job_queue.run_once(schedule_posts, 0)
    
    logger.info("بات شروع شد")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
