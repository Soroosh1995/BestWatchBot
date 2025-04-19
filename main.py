import telegram
import asyncio
import os
import logging
import aiohttp
import random
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
from aiohttp import web, ClientTimeout
import urllib.parse
from datetime import datetime, timedelta
from google.api_core import exceptions as google_exceptions
from openai import AsyncOpenAI
import aiohttp.client_exceptions
import re
import certifi

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
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
PORT = int(os.getenv('PORT', 8080))

# تنظیم Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# تنظیم Open AI
client = AsyncOpenAI(api_key=OPENAI_API_KEY, http_client=aiohttp.ClientSession(verify_ssl=certifi.where()))

# --- کش و متغیرهای سراسری ---
cached_movies = []
posted_movies = []
last_fetch_time = datetime.now() - timedelta(days=1)
previous_plots = []
previous_comments = []
gemini_available = True
openai_available = True
bot_enabled = True

# --- دیکشنری ترجمه ژانرها ---
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
    'Science Fiction': 'علمی_تخیلی',
    'Thriller': 'هیجان_انگیز',
    'War': 'جنگی',
    'Western': 'وسترن'
}

# --- فال‌بک‌ها ---
FALLBACK_PLOTS = {
    'اکشن': [
        "ماجراجویی پرهیجانی که قهرمان با دشمنان قدرتمند روبرو می‌شود. نبردهای نفس‌گیر شما را میخکوب می‌کند. آیا او می‌تواند جهان را نجات دهد؟",
    ],
    'درام': [
        "داستانی عمیق از روابط انسانی و انتخاب‌های سخت. زندگی شخصیتی پیچیده که قلب شما را لمس می‌کند. آیا او راه خود را پیدا خواهد کرد؟",
    ],
    'کمدی': [
        "ماجراهای خنده‌داری که زندگی را زیرورو می‌کنند. گروهی از دوستان که در موقعیت‌های عجیب گیر می‌افتند. آیا از این مخمصه خلاص می‌شوند؟",
    ],
    'علمی_تخیلی': [
        "جهانی در آینده که تکنولوژی همه‌چیز را تغییر داده. ماجراجویی‌ای برای کشف حقیقت پشت یک راز بزرگ. آیا بشریت نجات پیدا می‌کند؟",
    ]
}

FALLBACK_COMMENTS = {
    'اکشن': [
        "این فیلم با صحنه‌های اکشن نفس‌گیر و داستان پرهیجان، شما را به صندلی میخکوب می‌کند. کارگردانی پویا و جلوه‌های بصری خیره‌کننده از نقاط قوت آن است. فقط گاهی ریتم تند ممکن است کمی گیج‌کننده باشد.",
    ],
    'درام': [
        "این فیلم با داستانی عمیق و احساسی، قلب شما را تسخیر می‌کند. بازیگری بی‌نقص و کارگردانی حساس، آن را به اثری ماندگار تبدیل کرده‌اند. فقط ریتم کند برخی صحنه‌ها ممکن است صبر شما را بیازماید.",
    ],
    'کمدی': [
        "این فیلم با شوخی‌های بامزه و داستان سرگرم‌کننده، شما را به خنده می‌اندازد. بازیگران شیمی فوق‌العاده‌ای دارند و کارگردانی پرانرژی است. فقط برخی جوک‌ها ممکن است تکراری به نظر برسند.",
    ],
    'علمی_تخیلی': [
        "این فیلم با داستانی خلاقانه و جلوه‌های بصری خیره‌کننده، شما را به دنیایی دیگر می‌برد. کارگردانی هوشمندانه و موسیقی متن حماسی از نقاط قوت آن است. فقط برخی مفاهیم ممکن است پیچیده باشند.",
    ]
}

FALLBACK_MOVIE = {
    'title': 'Inception',
    'year': '2010',
    'plot': 'دزدی که اسرار شرکت‌ها را با فناوری رویا می‌دزدد، باید ایده‌ای در ذهن یک مدیر بکارد. گذشته غم‌انگیز او ممکن است پروژه را به فاجعه بکشاند.',
    'imdb': '8.8/10',
    'trailer': 'https://www.youtube.com/watch?v=YoHD9XEInc0',
    'poster': 'https://m.media-amazon.com/images/M/MV5BMjAxMzY3NjcxNF5BMl5BanBnXkFtZTcwNTI5OTM0Mw@@._V1_SX300.jpg',
    'comment': 'این فیلم اثری جذاب در ژانر علمی_تخیلی است که با داستانی پیچیده و جلوه‌های بصری خیره‌کننده، ذهن را به چالش می‌کشد. بازیگری و کارگردانی بی‌نقص، آن را فراموش‌نشدنی کرده‌اند. تنها ضعف، ریتم کند برخی صحنه‌هاست.',
    'rating': 4,
    'special': True,
    'genres': ['علمی_تخیلی', 'هیجان_انگیز']
}

# --- توابع کمکی ---
def clean_text(text):
    if not text or text == 'N/A':
        return None
    return text[:300]

def shorten_plot(text, max_sentences=3):
    sentences = [s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟']
    return '. '.join(sentences[:max_sentences]) + ('.' if sentences else '')

def is_farsi(text):
    farsi_chars = r'[\u0600-\u06FF]'
    return bool(re.search(farsi_chars, text))

def is_valid_plot(text):
    if not text or len(text.split()) < 5:
        return False
    sentences = text.split('. ')
    return len([s for s in sentences if s.strip() and s.strip()[-1] in '.!؟']) >= 1

def get_fallback_by_genre(options, genres):
    for genre in genres:
        if genre in options:
            available = [opt for opt in options[genre] if opt not in previous_comments]
            if available:
                return random.choice(available)
    available = [opt for genre in options for opt in options[genre] if opt not in previous_comments]
    return random.choice(available) if available else options[list(options.keys())[0]][0]

async def get_imdb_score_rapidapi(title, retries=5):
    logger.info(f"دریافت امتیاز RapidAPI برای: {title}")
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=15)) as session:
                encoded_title = urllib.parse.quote(title)
                url = f"https://imdb-api.com/en/API/SearchMovie/{RAPIDAPI_KEY}/{encoded_title}"
                async with session.get(url) as response:
                    if response.status == 429:
                        logger.warning(f"خطای 429: Rate Limit برای RapidAPI، تلاش {attempt + 1}")
                        await asyncio.sleep(3)
                        continue
                    if response.status == 401:
                        logger.error(f"خطای 401: کلید RapidAPI نامعتبر")
                        return None
                    data = await response.json()
                    logger.info(f"پاسخ RapidAPI برای {title}: {data}")
                    if not data.get('results'):
                        logger.warning(f"RapidAPI هیچ نتیجه‌ای برای {title} نداد")
                        return None
                    movie = data['results'][0]
                    imdb_score = movie.get('imDbRating', '0')
                    if float(imdb_score) < 6.0:
                        logger.warning(f"فیلم {title} امتیاز {imdb_score} دارد، رد شد")
                        return None
                    return f"{float(imdb_score):.1f}/10"
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.error(f"خطای اتصال RapidAPI برای {title} (تلاش {attempt + 1}): {str(e)}")
            if attempt == retries - 1:
                logger.error("تلاش‌های RapidAPI تمام شد")
                return None
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"خطا در RapidAPI برای {title} (تلاش {attempt + 1}): {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(3)
    return None

async def get_imdb_score_tmdb(title):
    logger.info(f"دریافت اطلاعات TMDB برای: {title}")
    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
            encoded_title = urllib.parse.quote(title)
            search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=en-US"
            async with session.get(search_url) as response:
                if response.status == 429:
                    logger.warning(f"خطای 429: Rate Limit برای TMDB")
                    return None
                data = await response.json()
                logger.info(f"پاسخ TMDB برای {title}: {data}")
                if not data.get('results'):
                    logger.warning(f"TMDB هیچ نتیجه‌ای برای {title} نداد")
                    return None
                movie = data['results'][0]
                imdb_score = movie.get('vote_average', 0)
                if imdb_score < 6.0:
                    logger.warning(f"فیلم {title} امتیاز {imdb_score} دارد، رد شد")
                    return None
                return f"{float(imdb_score):.1f}/10"
    except Exception as e:
        logger.error(f"خطا در TMDB برای {title}: {str(e)}")
        return None

async def get_imdb_score_omdb(title):
    logger.info(f"دریافت اطلاعات OMDb برای: {title}")
    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
            encoded_title = urllib.parse.quote(title)
            url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_title}&type=movie"
            async with session.get(url) as response:
                if response.status == 429:
                    logger.warning(f"خطای 429: Rate Limit برای OMDb")
                    return None
                data = await response.json()
                logger.info(f"پاسخ OMDb برای {title}: {data}")
                if data.get('Response') == 'False':
                    logger.warning(f"OMDb هیچ نتیجه‌ای برای {title} نداد: {data.get('Error')}")
                    return None
                imdb_score = data.get('imdbRating', '0')
                if float(imdb_score) < 6.0:
                    logger.warning(f"فیلم {title} امتیاز {imdb_score} دارد، رد شد")
                    return None
                return f"{float(imdb_score):.1f}/10"
    except Exception as e:
        logger.error(f"خطا در OMDb برای {title}: {str(e)}")
        return None

async def get_movie_info(title):
    logger.info(f"دریافت اطلاعات برای فیلم: {title}")
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=15)) as session:
                # 1. RapidAPI
                logger.info(f"تلاش با RapidAPI برای {title}")
                rapidapi_score = await get_imdb_score_rapidapi(title)
                if rapidapi_score:
                    encoded_title = urllib.parse.quote(title)
                    rapidapi_url = f"https://imdb-api.com/en/API/SearchMovie/{RAPIDAPI_KEY}/{encoded_title}"
                    async with session.get(rapidapi_url) as rapidapi_response:
                        rapidapi_data = await rapidapi_response.json()
                        logger.info(f"پاسخ RapidAPI برای {title}: {rapidapi_data}")
                        if rapidapi_data.get('results'):
                            movie = rapidapi_data['results'][0]
                            genres = movie.get('genres', '').split(', ')
                            genres = [GENRE_TRANSLATIONS.get(g, g) for g in genres]
                            return {
                                'title': movie.get('title', title),
                                'year': movie.get('description', '')[:4],
                                'plot': get_fallback_by_genre(FALLBACK_PLOTS, genres),
                                'imdb': rapidapi_score,
                                'trailer': None,
                                'poster': movie.get('image', None),
                                'genres': genres[:3]
                            }

                # 2. TMDB
                logger.info(f"تلاش با TMDB برای {title}")
                search_url_en = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=en-US"
                async with session.get(search_url_en) as tmdb_response_en:
                    if tmdb_response_en.status == 429:
                        logger.warning(f"خطای 429: Rate Limit برای TMDB، تلاش {attempt + 1}")
                        await asyncio.sleep(3)
                        continue
                    tmdb_data_en = await tmdb_response_en.json()
                    logger.info(f"پاسخ TMDB (انگلیسی) برای {title}: {tmdb_data_en}")
                    if tmdb_data_en.get('results'):
                        movie = tmdb_data_en['results'][0]
                        movie_id = movie.get('id')
                        tmdb_title = movie.get('title', title)
                        tmdb_poster = f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else None
                        
                        details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
                        async with session.get(details_url) as details_response:
                            details_data = await details_response.json()
                            genres = [GENRE_TRANSLATIONS.get(g['name'], g['name']) for g in details_data.get('genres', [])]
                        
                        search_url_fa = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=fa-IR"
                        async with session.get(search_url_fa) as tmdb_response_fa:
                            tmdb_data_fa = await tmdb_response_fa.json()
                            tmdb_plot = tmdb_data_fa['results'][0].get('overview', '') if tmdb_data_fa.get('results') else ''
                            tmdb_year = tmdb_data_fa['results'][0].get('release_date', 'N/A')[:4] if tmdb_data_fa.get('results') else 'N/A'
                        
                        trailer = None
                        videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}&language=en"
                        async with session.get(videos_url) as videos_response:
                            videos_data = await videos_response.json()
                            if videos_data.get('results'):
                                for video in videos_data['results']:
                                    if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                        trailer = f"https://www.youtube.com/watch?v={video['key']}"
                                        break
                        
                        imdb_score = await get_imdb_score_omdb(tmdb_title) or await get_imdb_score_tmdb(tmdb_title)
                        if not imdb_score:
                            logger.warning(f"امتیاز معتبر برای {tmdb_title} یافت نشد")
                            continue
                        
                        plot = shorten_plot(tmdb_plot) if tmdb_plot and is_farsi(tmdb_plot) else get_fallback_by_genre(FALLBACK_PLOTS, genres)
                        previous_plots.append(plot)
                        if len(previous_plots) > 10:
                            previous_plots.pop(0)
                        
                        return {
                            'title': tmdb_title,
                            'year': tmdb_year,
                            'plot': plot,
                            'imdb': imdb_score,
                            'trailer': trailer,
                            'poster': tmdb_poster,
                            'genres': genres[:3]
                        }

                # 3. OMDb
                logger.info(f"تلاش با OMDb برای {title}")
                omdb_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_title}&type=movie"
                async with session.get(omdb_url) as omdb_response:
                    if omdb_response.status == 429:
                        logger.warning(f"خطای 429: Rate Limit برای OMDb، تلاش {attempt + 1}")
                        await asyncio.sleep(3)
                        continue
                    omdb_data = await omdb_response.json()
                    logger.info(f"پاسخ OMDb برای {title}: {omdb_data}")
                    if omdb_data.get('Response') == 'True':
                        imdb_score = omdb_data.get('imdbRating', '0')
                        if float(imdb_score) >= 6.0:
                            genres = omdb_data.get('Genre', '').split(', ')
                            genres = [GENRE_TRANSLATIONS.get(g.strip(), g.strip()) for g in genres]
                            return {
                                'title': omdb_data.get('Title', title),
                                'year': omdb_data.get('Year', 'N/A'),
                                'plot': omdb_data.get('Plot', get_fallback_by_genre(FALLBACK_PLOTS, genres)),
                                'imdb': f"{float(imdb_score):.1f}/10",
                                'trailer': None,
                                'poster': omdb_data.get('Poster', None),
                                'genres': genres[:3]
                            }
                
                logger.warning(f"هیچ API برای {title} جواب نداد، تلاش {attempt + 1}")
        except Exception as e:
            logger.error(f"خطا در دریافت اطلاعات فیلم {title} (تلاش {attempt + 1}): {str(e)}")
            await asyncio.sleep(3)
    
    logger.error(f"هیچ اطلاعاتی برای {title} یافت نشد")
    return None

async def generate_comment(genres):
    global gemini_available, openai_available
    logger.info("تولید تحلیل...")
    
    if gemini_available:
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = "یک تحلیل کوتاه و جذاب به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، در 3 جمله کامل (هر جمله با نقطه پایان یابد). لحن حرفه‌ای و سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد."
                response = await model.generate_content_async(prompt)
                text = response.text.strip()
                sentences = [s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟']
                if len(sentences) >= 3 and is_farsi(text) and len(text.split()) > 15:
                    previous_comments.append(text)
                    if len(previous_comments) > 10:
                        previous_comments.pop(0)
                    return '. '.join(sentences[:3]) + '.'
                logger.warning(f"تحلیل Gemini نامعتبر (تلاش {attempt + 1}): {text}")
            except google_exceptions.ResourceExhausted as e:
                logger.error(f"خطا: توکن Gemini تمام شده است: {str(e)}")
                gemini_available = False
                await send_admin_alert(None, "❌ توکن Gemini تمام شده است. تلاش با Open AI...")
            except Exception as e:
                logger.error(f"خطا در Gemini API (تلاش {attempt + 1}): {str(e)}")
    
    if openai_available:
        for attempt in range(5):
            try:
                response = await client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a professional film critic writing in Persian."},
                        {"role": "user", "content": "یک تحلیل کوتاه و جذاب به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، در 3 جمله کامل (هر جمله با نقطه پایان یابد). لحن حرفه‌ای و سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد. فقط به فارسی بنویس و از کلمات انگلیسی استفاده نکن."}
                    ],
                    max_tokens=150,
                    temperature=0.7,
                    timeout=20
                )
                text = response.choices[0].message.content.strip()
                sentences = [s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟']
                if len(sentences) >= 3 and is_farsi(text) and len(text.split()) > 15:
                    previous_comments.append(text)
                    if len(previous_comments) > 10:
                        previous_comments.pop(0)
                    return '. '.join(sentences[:3]) + '.'
                logger.warning(f"تحلیل Open AI نامعتبر: {text}")
            except aiohttp.client_exceptions.ClientConnectorError as e:
                logger.error(f"خطای اتصال Open AI (تلاش {attempt + 1}): {str(e)}")
                if attempt == 4:
                    openai_available = False
                    await send_admin_alert(None, "❌ مشکل اتصال به Open AI. هیچ تحلیلگر دیگری در دسترس نیست.")
            except Exception as e:
                logger.error(f"خطا در Open AI API (تلاش {attempt + 1}): {str(e)}")
                if attempt == 4:
                    openai_available = False
                    await send_admin_alert(None, f"❌ خطا در Open AI: {str(e)}")
            await asyncio.sleep(3)
    
    logger.warning("هیچ تحلیلگری در دسترس نیست، استفاده از فال‌بک")
    comment = get_fallback_by_genre(FALLBACK_COMMENTS, genres)
    previous_comments.append(comment)
    if len(previous_comments) > 10:
        previous_comments.pop(0)
    return comment

async def send_admin_alert(context: ContextTypes.DEFAULT_TYPE, message: str):
    try:
        if context:
            await context.bot.send_message(ADMIN_ID, message)
        else:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                payload = {"chat_id": ADMIN_ID, "text": message}
                async with session.post(url, json=payload) as response:
                    result = await response.json()
                    if not result.get('ok'):
                        logger.error(f"خطا در ارسال هشدار به ادمین: {result}")
    except Exception as e:
        logger.error(f"خطا در ارسال هشدار به ادمین: {str(e)}")

async def fetch_movies_to_cache():
    global cached_movies, last_fetch_time
    logger.info("شروع آپدیت کش فیلم‌ها...")
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
                new_movies = []
                page = 1
                while len(new_movies) < 100 and page <= 5:
                    # 1. TMDB (اولویت تا RapidAPI درست شه)
                    logger.info(f"تلاش با TMDB برای کش، صفحه {page}")
                    tmdb_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page={page}"
                    async with session.get(tmdb_url) as tmdb_response:
                        if tmdb_response.status == 429:
                            logger.warning(f"خطای 429: Rate Limit برای TMDB، تلاش {attempt + 1}")
                            await asyncio.sleep(3)
                            continue
                        tmdb_data = await tmdb_response.json()
                        logger.info(f"پاسخ TMDB برای کش: {tmdb_data}")
                        if 'results' in tmdb_data and tmdb_data['results']:
                            for m in tmdb_data['results']:
                                if (m.get('title') and m.get('id') and
                                    m.get('original_language') != 'hi' and
                                    'IN' not in m.get('origin_country', []) and
                                    m.get('poster_path')):
                                    imdb_score = await get_imdb_score_omdb(m['title']) or await get_imdb_score_tmdb(m['title'])
                                    if imdb_score and float(imdb_score.split('/')[0]) >= 6.0:
                                        new_movies.append({'title': m['title'], 'id': m['id']})
                            page += 1

                    # 2. OMDb
                    logger.info(f"تلاش با OMDb برای کش، صفحه {page}")
                    omdb_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&s=movie&type=movie&page={page}"
                    async with session.get(omdb_url) as omdb_response:
                        if omdb_response.status == 429:
                            logger.warning(f"خطای 429: Rate Limit برای OMDb، تلاش {attempt + 1}")
                            await asyncio.sleep(3)
                            continue
                        omdb_data = await omdb_response.json()
                        logger.info(f"پاسخ OMDb برای کش: {omdb_data}")
                        if omdb_data.get('Search'):
                            for m in omdb_data['Search']:
                                imdb_score = await get_imdb_score_omdb(m['Title'])
                                if imdb_score and float(imdb_score.split('/')[0]) >= 6.0:
                                    new_movies.append({'title': m['Title'], 'id': m['imdbID']})
                            page += 1

                    # 3. RapidAPI
                    logger.info(f"تلاش با RapidAPI برای کش، صفحه {page}")
                    rapidapi_url = f"https://imdb-api.com/en/API/MostPopularMovies/{RAPIDAPI_KEY}"
                    async with session.get(rapidapi_url) as rapidapi_response:
                        if rapidapi_response.status == 429:
                            logger.warning(f"خطای 429: Rate Limit برای RapidAPI، تلاش {attempt + 1}")
                            await asyncio.sleep(3)
                            continue
                        rapidapi_data = await rapidapi_response.json()
                        logger.info(f"پاسخ RapidAPI برای کش: {rapidapi_data}")
                        if rapidapi_data.get('items'):
                            for m in rapidapi_data['items']:
                                if float(m.get('imDbRating', 0)) >= 6.0:
                                    new_movies.append({'title': m['title'], 'id': m['id']})
                            break
                
                if new_movies:
                    cached_movies = new_movies[:100]
                    last_fetch_time = datetime.now()
                    logger.info(f"لیست فیلم‌ها آپدیت شد. تعداد: {len(cached_movies)}")
                    return True
                logger.error("داده‌ای از هیچ API دریافت نشد")
                cached_movies = [{'title': 'Inception', 'id': 'tt1375666'}, {'title': 'The Matrix', 'id': 'tt0133093'}]
                last_fetch_time = datetime.now()
                return False
        except Exception as e:
            logger.error(f"خطا در آپدیت کش (تلاش {attempt + 1}): {str(e)}")
            await asyncio.sleep(3)
    
    logger.error("تلاش‌ها برای آپدیت کش ناموفق بود")
    cached_movies = [{'title': 'Inception', 'id': 'tt1375666'}, {'title': 'The Matrix', 'id': 'tt0133093'}]
    last_fetch_time = datetime.now()
    return False

async def auto_fetch_movies(context: ContextTypes.DEFAULT_TYPE):
    logger.info("شروع آپدیت خودکار کش...")
    if await fetch_movies_to_cache():
        logger.info("آپدیت خودکار کش موفق بود")
    else:
        logger.error("خطا در آپدیت خودکار کش")
        await send_admin_alert(context, "❌ خطا در آپدیت خودکار کش")

async def get_random_movie(max_retries=3):
    logger.info("انتخاب فیلم تصادفی...")
    for attempt in range(max_retries):
        try:
            if not cached_movies or (datetime.now() - last_fetch_time).seconds > 86400:
                logger.info("کش خالی یا قدیمی، آپدیت کش...")
                await fetch_movies_to_cache()
            
            if not cached_movies:
                logger.error("هیچ فیلمی در کش موجود نیست، استفاده از فال‌بک")
                return FALLBACK_MOVIE
            
            available_movies = [m for m in cached_movies if m['id'] not in posted_movies]
            if not available_movies:
                logger.warning("هیچ فیلم جدیدی در کش نیست، ریست لیست پست‌شده‌ها")
                posted_movies.clear()
                available_movies = cached_movies
            
            movie = random.choice(available_movies)
            logger.info(f"فیلم انتخاب شد: {movie['title']} (تلاش {attempt + 1})")
            movie_info = await get_movie_info(movie['title'])
            if not movie_info or movie_info['imdb'] == '0.0/10':
                logger.warning(f"اطلاعات فیلم {movie['title']} نامعتبر، تلاش مجدد...")
                continue
            
            posted_movies.append(movie['id'])
            comment = await generate_comment(movie_info['genres'])
            if not comment:
                logger.error("تحلیل تولید نشد، استفاده از فال‌بک")
                comment = get_fallback_by_genre(FALLBACK_COMMENTS, movie_info['genres'])
            
            imdb_score = float(movie_info['imdb'].split('/')[0])
            logger.info(f"امتیاز برای {movie['title']}: {imdb_score}")
            if imdb_score >= 8.5:
                rating = 5
            elif 7.5 <= imdb_score < 8.5:
                rating = 4
            elif 6.5 <= imdb_score < 7.5:
                rating = 3
            elif 6.0 <= imdb_score < 6.5:
                rating = 2
            else:
                rating = 1
            
            return {
                **movie_info,
                'comment': comment,
                'rating': rating,
                'special': imdb_score >= 8.5
            }
        except Exception as e:
            logger.error(f"خطا در انتخاب فیلم (تلاش {attempt + 1}): {str(e)}")
            if attempt == max_retries - 1:
                logger.error("تلاش‌ها تمام شد، استفاده از فال‌بک")
                return FALLBACK_MOVIE
    logger.error("تلاش‌ها تمام شد، استفاده از فال‌بک")
    return FALLBACK_MOVIE

def format_movie_post(movie):
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie['special'] else ''
    channel_link = 'https://t.me/bestwatch_channel'
    rlm = '\u200F'
    genres = ' '.join([f"#{g.replace(' ', '_')}" for g in movie['genres']]) if movie['genres'] else '#سینمایی'
    
    post_sections = [
        f"""
🎬 <b>عنوان فیلم:</b>
<b>{clean_text(movie['title']) or 'بدون عنوان'}{special}</b>

📅 <b>سال تولید: {clean_text(movie['year']) or 'نامشخص'}</b>
"""
    ]
    
    if movie['plot'] and clean_text(movie['plot']) != 'متن موجود نیست':
        post_sections.append(f"""
📝 <b>خلاصه داستان:</b>
{rlm}{clean_text(movie['plot'])}
""")
    
    post_sections.append(f"""
🌟 <b>امتیاز IMDB:</b>
<b>{clean_text(movie['imdb']) or 'نامشخص'}</b>
""")
    
    if movie['trailer'] and movie['trailer'].startswith('http'):
        post_sections.append(f"""
🎞 <b>لینک تریلر:</b>
{clean_text(movie['trailer'])}
""")
    
    if movie['comment']:
        post_sections.append(f"""
🍿 <b>حرف ما:</b>
{rlm}{clean_text(movie['comment'])}
""")
    
    post_sections.append(f"""
🎯 <b>ارزش دیدن: {stars}</b>

{genres}

{channel_link}
""")
    
    return ''.join(post_sections)

def get_main_menu():
    toggle_text = "غیرفعال کردن ربات" if bot_enabled else "فعال کردن ربات"
    keyboard = [
        [
            InlineKeyboardButton("آپدیت لیست", callback_data='fetch_movies'),
            InlineKeyboardButton("ارسال فوری", callback_data='post_now')
        ],
        [
            InlineKeyboardButton("تست‌ها", callback_data='tests_menu'),
            InlineKeyboardButton("آمار بازدید", callback_data='stats')
        ],
        [
            InlineKeyboardButton(toggle_text, callback_data='toggle_bot'),
            InlineKeyboardButton("ریست Webhook", callback_data='reset_webhook')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_tests_menu():
    keyboard = [
        [
            InlineKeyboardButton("دسترسی فنی", callback_data='test_all'),
            InlineKeyboardButton("دسترسی کانال", callback_data='test_channel')
        ],
        [
            InlineKeyboardButton("بازگشت", callback_data='back_to_main')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        logger.info(f"دسترسی غیرمجاز توسط کاربر: {update.message.from_user.id}")
        return
    logger.info("دستور /start اجرا شد")
    await update.message.reply_text("🤖 منوی ادمین", reply_markup=get_main_menu())

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        logger.info(f"دسترسی غیرمجاز برای debug: {update.message.from_user.id}")
        return
    logger.info("اجرای debug")
    try:
        update_dict = update.to_dict()
        callback_query = update.callback_query
        callback_data = callback_query.data if callback_query else "هیچ callback_query"
        await update.message.reply_text(
            f"ساختار آپدیت:\n{update_dict}\n\nCallbackQuery: {callback_query}\nCallbackData: {callback_data}"
        )
    except Exception as e:
        logger.error(f"خطا در دیباگ: {str(e)}")
        await update.message.reply_text(f"❌ خطا در دیباگ: {str(e)}")

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه back_to_main")
    await query.answer()
    try:
        await query.message.edit_text("🤖 منوی ادمین", reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"خطا در back_to_main: {str(e)}")
        await query.message.edit_text(f"❌ خطا: {str(e)}", reply_markup=get_main_menu())

async def tests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه tests_menu")
    await query.answer()
    try:
        await query.message.edit_text("🛠 منوی تست‌ها", reply_markup=get_tests_menu())
    except Exception as e:
        logger.error(f"خطا در tests_menu: {str(e)}")
        await query.message.edit_text(f"❌ خطا: {str(e)}", reply_markup=get_main_menu())

async def fetch_movies_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه fetch_movies")
    await query.answer()
    msg = await query.message.edit_text("در حال آپدیت لیست...")
    try:
        if await fetch_movies_to_cache():
            keyboard = [
                [
                    InlineKeyboardButton("لیست فیلم‌ها", callback_data='show_movies'),
                    InlineKeyboardButton("بازگشت", callback_data='back_to_main')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await msg.edit_text(f"✅ لیست آپدیت شد! ({len(cached_movies)} فیلم)", reply_markup=reply_markup)
        else:
            await msg.edit_text("❌ خطا در آپدیت لیست", reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"خطا در fetch_movies: {str(e)}")
        await msg.edit_text(f"❌ خطا: {str(e)}", reply_markup=get_main_menu())

async def post_now_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه post_now")
    await query.answer()
    msg = await query.message.edit_text("در حال آماده‌سازی پست...")
    try:
        if not bot_enabled:
            logger.error("ارسال پست کنسل شد: ربات غیرفعال است")
            await msg.edit_text("❌ ارسال پست کنسل شد: ربات غیرفعال است", reply_markup=get_main_menu())
            return
        movie = await get_random_movie()
        if not movie:
            logger.error("هیچ فیلمی انتخاب نشد")
            await msg.edit_text("❌ خطا در یافتن فیلم", reply_markup=get_main_menu())
            return
        
        logger.info(f"ارسال پست برای: {movie['title']}")
        if movie['poster']:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=movie['poster'],
                caption=format_movie_post(movie),
                parse_mode='HTML',
                disable_notification=True
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=format_movie_post(movie),
                parse_mode='HTML',
                disable_notification=True
            )
        await msg.edit_text(f"✅ پست {movie['title']} ارسال شد", reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"خطا در post_now: {e}")
        await msg.edit_text(f"❌ خطا در ارسال پست: {str(e)}", reply_markup=get_main_menu())

async def test_all_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه test_all")
    await query.answer()
    msg = await query.message.edit_text("در حال تست سرویس‌ها...")
    results = []
    
    # تست RapidAPI
    for attempt in range(5):
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=15)) as session:
                url = f"https://imdb-api.com/en/API/SearchMovie/{RAPIDAPI_KEY}/test"
                async with session.get(url) as response:
                    data = await response.json()
                    rapidapi_status = "✅ RapidAPI اوکی" if data.get('results') or data.get('errorMessage') else f"❌ RapidAPI خطا: {data}"
                    results.append(rapidapi_status)
                    break
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.error(f"خطای اتصال RapidAPI (تلاش {attempt + 1}): {str(e)}")
            if attempt == 4:
                results.append(f"❌ RapidAPI خطا: {str(e)}")
        except Exception as e:
            logger.error(f"خطا در RapidAPI (تلاش {attempt + 1}): {str(e)}")
            if attempt == 4:
                results.append(f"❌ RapidAPI خطا: {str(e)}")
        await asyncio.sleep(3)

    # تست TMDB
    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
            tmdb_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=fa-IR&page=1"
            async with session.get(tmdb_url) as tmdb_res:
                tmdb_data = await tmdb_res.json()
                tmdb_status = "✅ TMDB اوکی" if tmdb_data.get('results') else f"❌ TMDB خطا: {tmdb_data}"
        results.append(tmdb_status)
    except Exception as e:
        results.append(f"❌ TMDB خطا: {str(e)}")

    # تست OMDb
    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
            omdb_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t=Inception&type=movie"
            async with session.get(omdb_url) as omdb_res:
                omdb_data = await omdb_res.json()
                omdb_status = "✅ OMDb اوکی" if omdb_data.get('Response') == 'True' else f"❌ OMDb خطا: {omdb_data.get('Error')}"
        results.append(omdb_status)
    except Exception as e:
        results.append(f"❌ OMDb خطا: {str(e)}")

    # تست JobQueue
    job_queue = context.job_queue
    results.append("✅ JobQueue فعال" if job_queue else "❌ JobQueue غیرفعال")

    # تست Gemini
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = "تست: یک جمله به فارسی بنویس."
        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        gemini_status = "✅ Gemini اوکی" if text and is_farsi(text) else "❌ Gemini خطا: پاسخ نامعتبر"
        results.append(gemini_status)
    except Exception as e:
        logger.error(f"خطا در تست Gemini: {str(e)}")
        results.append(f"❌ Gemini خطا: {str(e)}")

    # تست Open AI
    for attempt in range(5):
        try:
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Write in Persian."},
                    {"role": "user", "content": "تست: یک جمله به فارسی بنویس."}
                ],
                max_tokens=50,
                temperature=0.7,
                timeout=20
            )
            text = response.choices[0].message.content.strip()
            openai_status = "✅ Open AI اوکی" if text and is_farsi(text) else "❌ Open AI خطا: پاسخ نامعتبر"
            results.append(openai_status)
            break
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.error(f"خطای اتصال Open AI (تلاش {attempt + 1}): {str(e)}")
            if attempt == 4:
                results.append(f"❌ Open AI خطا: Connection error")
        except Exception as e:
            logger.error(f"خطا در تست Open AI (تلاش {attempt + 1}): {str(e)}")
            if attempt == 4:
                results.append(f"❌ Open AI خطا: {str(e)}")
        await asyncio.sleep(3)
    
    await msg.edit_text("\n".join(results), reply_markup=get_tests_menu())

async def test_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه test_channel")
    await query.answer()
    msg = await query.message.edit_text("در حال تست دسترسی به کانال...")
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember?chat_id={CHANNEL_ID}&user_id={context.bot.id}"
            async with session.get(url) as response:
                data = await response.json()
                if not data.get('ok'):
                    raise Exception(f"خطا در API تلگرام: {data.get('description')}")
                if data['result']['status'] not in ['administrator', 'creator']:
                    raise Exception("بات ادمین کانال نیست.")
        await msg.edit_text("✅ دسترسی به کانال اوکی", reply_markup=get_tests_menu())
    except Exception as e:
        logger.error(f"خطا در تست دسترسی به کانال: {str(e)}")
        await msg.edit_text(f"❌ خطا در تست دسترسی به کانال: {str(e)}", reply_markup=get_tests_menu())

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه stats")
    await query.answer()
    msg = await query.message.edit_text("در حال بررسی بازدید کانال...")
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember?chat_id={CHANNEL_ID}&user_id={context.bot.id}"
            async with session.get(url) as response:
                data = await response.json()
                if not data.get('ok') or data['result']['status'] not in ['administrator', 'creator']:
                    raise Exception("بات ادمین کانال نیست.")
        
        now = datetime.now()
        views_week = []
        
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset=-100"
            async with session.get(url) as response:
                data = await response.json()
                if not data.get('ok') or not data.get('result'):
                    raise Exception("هیچ پیامی دریافت نشد. لطفاً حداقل یک پست در کانال منتشر کنید.")
                
                for update in data['result']:
                    if 'channel_post' in update:
                        post = update['channel_post']
                        if post.get('chat', {}).get('id') != int(CHANNEL_ID.replace('@', '')):
                            continue
                        if not post.get('views'):
                            continue
                        message_time = datetime.fromtimestamp(post['date'])
                        time_diff = now - message_time
                        if time_diff <= timedelta(days=7):
                            views_week.append(post['views'])
        
        if not views_week:
            raise Exception("هیچ پستی در 7 روز اخیر یافت نشد. لطفاً حداقل یک پست منتشر کنید.")
        
        avg_week = sum(views_week) / len(views_week)
        
        result = f"📊 آمار بازدید کانال:\n- میانگین بازدید 7 روز اخیر: {avg_week:.1f}"
        await msg.edit_text(result, reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"خطا در بررسی بازدید: {str(e)}")
        await msg.edit_text(f"❌ خطا در بررسی بازدید: {str(e)}", reply_markup=get_main_menu())

async def show_movies_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه show_movies")
    await query.answer()
    try:
        if not cached_movies:
            await query.message.edit_text("❌ لیست فیلم‌ها خالی است", reply_markup=get_main_menu())
            return
        
        movies_list = "\n".join([f"{i+1}. {m['title']}" for i, m in enumerate(cached_movies)])
        keyboard = [[InlineKeyboardButton("بازگشت", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(f"📋 لیست فیلم‌ها:\n{movies_list}", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"خطا در show_movies: {str(e)}")
        await query.message.edit_text(f"❌ خطا: {str(e)}", reply_markup=get_main_menu())

async def toggle_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_enabled
    query = update.callback_query
    logger.info("دکمه toggle_bot")
    await query.answer()
    try:
        bot_enabled = not bot_enabled
        status = "فعال" if bot_enabled else "غیرفعال"
        await query.message.edit_text(f"✅ ربات {status} شد", reply_markup=get_main_menu())
        await send_admin_alert(context, f"🤖 ربات {status} شد")
    except Exception as e:
        logger.error(f"خطا در toggle_bot: {str(e)}")
        await query.message.edit_text(f"❌ خطا: {str(e)}", reply_markup=get_main_menu())

async def reset_webhook_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه reset_webhook")
    await query.answer()
    msg = await query.message.edit_text("در حال ریست Webhook...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
                json={"drop_pending_updates": True}
            ) as response:
                result = await response.json()
                if result.get('ok'):
                    await msg.edit_text("✅ Webhook ریست شد", reply_markup=get_main_menu())
                else:
                    await msg.edit_text(f"❌ خطا در ریست Webhook: {result.get('description')}", reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"خطا در ریست Webhook: {e}")
        await msg.edit_text(f"❌ خطا در ریست Webhook: {str(e)}", reply_markup=get_main_menu())

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    logger.info("شروع پست خودکار...")
    try:
        if not bot_enabled:
            logger.info("پست خودکار کنسل شد: ربات غیرفعال است")
            return
        movie = await get_random_movie()
        if not movie:
            logger.error("هیچ فیلمی انتخاب نشد")
            await send_admin_alert(context, "❌ خطا: فیلم برای پست خودکار یافت نشد")
            return
        
        logger.info(f"فیلم انتخاب شد: {movie['title']}")
        if movie['poster']:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=movie['poster'],
                caption=format_movie_post(movie),
                parse_mode='HTML',
                disable_notification=True
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=format_movie_post(movie),
                parse_mode='HTML',
                disable_notification=True
            )
        logger.info(f"پست خودکار برای {movie['title']} ارسال شد")
    except Exception as e:
        logger.error(f"خطا در ارسال پست خودکار: {e}")
        await send_admin_alert(context, f"❌ خطای پست خودکار: {str(e)}")

async def health_check(request):
    return web.Response(text="OK")

async def run_web():
    logger.info(f"راه‌اندازی سرور وب روی پورت {PORT}...")
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"سرور وب روی پورت {PORT} فعال شد")
    return runner

async def run_bot():
    logger.info("شروع راه‌اندازی بات تلگرام...")
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("Application ساخته شد")
    except Exception as e:
        logger.error(f"خطا در ساخت Application: {str(e)}")
        raise
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("resetwebhook", reset_webhook_handler))
    
    app.add_handler(CallbackQueryHandler(back_to_main, pattern='^back_to_main$'))
    app.add_handler(CallbackQueryHandler(tests_menu, pattern='^tests_menu$'))
    app.add_handler(CallbackQueryHandler(fetch_movies_handler, pattern='^fetch_movies$'))
    app.add_handler(CallbackQueryHandler(post_now_handler, pattern='^post_now$'))
    app.add_handler(CallbackQueryHandler(test_all_handler, pattern='^test_all$'))
    app.add_handler(CallbackQueryHandler(test_channel_handler, pattern='^test_channel$'))
    app.add_handler(CallbackQueryHandler(stats_handler, pattern='^stats$'))
    app.add_handler(CallbackQueryHandler(show_movies_handler, pattern='^show_movies$'))
    app.add_handler(CallbackQueryHandler(toggle_bot_handler, pattern='^toggle_bot$'))
    app.add_handler(CallbackQueryHandler(reset_webhook_handler, pattern='^reset_webhook$'))
    
    job_queue = app.job_queue
    if job_queue:
        logger.info("JobQueue فعال شد")
        job_queue.run_repeating(auto_post, interval=600, first=10)
        job_queue.run_repeating(auto_fetch_movies, interval=86400, first=60)
    else:
        logger.error("JobQueue فعال نشد، استفاده از زمان‌بندی جایگزین")
        await send_admin_alert(None, "⚠️ هشدار: JobQueue فعال نشد، استفاده از زمان‌بندی جایگزین")
        asyncio.create_task(fallback_scheduler(app.context))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("بات تلگرام با موفقیت راه‌اندازی شد")
    return app

async def fallback_scheduler(context: ContextTypes.DEFAULT_TYPE):
    logger.info("اجرای زمان‌بندی جایگزین...")
    while True:
        await auto_post(context)
        await asyncio.sleep(600)
        if (datetime.now() - last_fetch_time).seconds > 86400:
            await auto_fetch_movies(context)

async def main():
    logger.info("شروع برنامه...")
    if not await fetch_movies_to_cache():
        logger.error("خطا در دریافت اولیه لیست فیلم‌ها")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
                json={"drop_pending_updates": True}
            ) as response:
                result = await response.json()
                logger.info(f"ریست Webhook: {result}")
    except Exception as e:
        logger.error(f"خطا در ریست Webhook اولیه: {e}")
    
    bot_app = await run_bot()
    web_runner = await run_web()
    
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("خاموش کردن بات...")
    finally:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        await web_runner.cleanup()

if __name__ == '__main__':
    asyncio.run(main())
