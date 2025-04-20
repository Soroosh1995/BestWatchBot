import telegram
import asyncio
import os
import json
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
import atexit

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
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
PORT = int(os.getenv('PORT', 8080))
POST_INTERVAL = int(os.getenv('POST_INTERVAL', 600))
FETCH_INTERVAL = int(os.getenv('FETCH_INTERVAL', 604800))  # هر 7 روز

# تنظیم Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# تنظیم Open AI
client = None

async def init_openai_client():
    global client
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# --- Cleanup برای خاموش‌سازی ---
def cleanup():
    logger.info("اجرای cleanup برای خاموش‌سازی...")
    if 'bot_app' in globals() and bot_app.running:
        asyncio.run(bot_app.updater.stop())
        asyncio.run(bot_app.stop())
        asyncio.run(bot_app.shutdown())
    if 'web_runner' in globals():
        asyncio.run(web_runner.cleanup())
    if client:
        asyncio.run(client.close())
    logger.info("Cleanup کامل شد")

atexit.register(cleanup)

# --- وضعیت دسترسی APIها و زمان قطعی ---
api_availability = {
    'gemini': True,
    'groq': True,
    'openai': True
}

api_downtime = {
    'gemini': None,
    'groq': None,
    'openai': None
}

# --- کش و متغیرهای سراسری ---
cached_movies = []
posted_movies = []
last_fetch_time = datetime.now() - timedelta(days=1)
previous_plots = []
previous_comments = []
bot_enabled = True
fallback_count = 0
api_cache = {}  # کش برای پاسخ‌های API
CACHE_FILE = "movie_cache.json"
POSTED_MOVIES_FILE = "posted_movies.json"

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
    'Western': 'وسترن',
    'Unknown': 'سایر'
}

# --- فال‌بک‌ها ---
FALLBACK_PLOTS = {
    'اکشن': [
        "ماجراجویی پرهیجانی که قهرمان با دشمنان قدرتمند روبرو می‌شود. نبردهای نفس‌گیر شما را میخکوب می‌کند. آیا او می‌تواند جهان را نجات دهد؟ پایان غیرمنتظره‌ای در انتظار است.",
        "داستانی پر از تعقیب و گریز و انفجارهای مهیج. قهرمانی که برای عدالت می‌جنگد. موانع غیرمنتظره‌ای پیش روی اوست. آیا او پیروز خواهد شد؟",
        "مبارزه‌ای حماسی برای نجات بشریت. صحنه‌های اکشن خیره‌کننده و داستانی پرتعلیق. چالش‌های بزرگی پیش روی قهرمان است. آیا پایان خوشی رقم خواهد خورد؟"
    ],
    'درام': [
        "داستانی عمیق از روابط انسانی و انتخاب‌های سخت. زندگی شخصیتی پیچیده که قلب شما را لمس می‌کند. تصمیمات او آینده را تغییر می‌دهند. آیا او راه خود را پیدا خواهد کرد؟",
        "روایتی احساسی از چالش‌های زندگی و عشق. شخصیت‌ها با مشکلات بزرگی روبرو می‌شوند. تصمیم‌هایی که آینده را تغییر می‌دهند. آیا پایان خوشی در انتظار است؟",
        "سفری احساسی در دل مشکلات زندگی. شخصیت‌هایی که با شجاعت مبارزه می‌کنند. روابط عمیقی که قلب را می‌فشارند. آیا امید پیروز می‌شود؟"
    ],
    'کمدی': [
        "ماجراهای خنده‌داری که زندگی را زیرورو می‌کنند. گروهی از دوستان که در موقعیت‌های عجیب گیر می‌افتند. شوخی‌های بامزه شما را سرگرم می‌کنند. آیا از این مخمصه خلاص می‌شوند؟",
        "داستانی پر از شوخی و موقعیت‌های بامزه. شخصیت‌هایی که شما را به خنده می‌اندازند. ماجراهای غیرمنتظره‌ای در انتظار است. آیا همه‌چیز به خیر می‌گذرد؟",
        "کمدی‌ای که با طنز هوشمندانه شما را سرگرم می‌کند. ماجراهایی که خنده را به لب‌هایتان می‌آورد. شخصیت‌های دوست‌داشتنی و موقعیت‌های خنده‌دار. آیا پایان شادی رقم می‌خورد؟"
    ],
    'علمی_تخیلی': [
        "جهانی در آینده که تکنولوژی همه‌چیز را تغییر داده. ماجراجویی‌ای برای کشف حقیقت پشت یک راز بزرگ. چالش‌های عجیبی پیش روی قهرمانان است. آیا بشریت نجات پیدا می‌کند؟",
        "داستانی از سفر در زمان و فضا. اکتشافاتی که جهان را دگرگون می‌کنند. موانع غیرمنتظره‌ای در مسیر است. آیا حقیقت آشکار خواهد شد؟",
        "ماجراجویی‌ای در فضایی ناشناخته. فناوری‌های عجیب و داستانی پیچیده. قهرمانان با خطراتی بزرگ روبرو می‌شوند. آیا موفق خواهند شد؟"
    ],
    'سایر': [
        "داستانی جذاب که شما را به سفری غیرمنتظره می‌برد. شخصیت‌هایی که با چالش‌های بزرگ روبرو می‌شوند. ماجراهایی که قلب و ذهن را درگیر می‌کنند. آیا پایان خوشی در انتظار است؟",
        "روایتی متفاوت که شما را غافلگیر می‌کند. ماجراهایی که قلب و ذهن را درگیر می‌کنند. شخصیت‌هایی که با شجاعت پیش می‌روند. آیا همه‌چیز درست می‌شود؟",
        "داستانی که شما را به دنیایی جدید می‌برد. شخصیت‌هایی که با مشکلات غیرمنتظره روبرو می‌شوند. ماجراهای هیجان‌انگیز و احساسی. آیا پایان رضایت‌بخشی خواهد داشت؟"
    ]
}

FALLBACK_COMMENTS = {
    'اکشن': [
        "این فیلم با صحنه‌های اکشن نفس‌گیر و داستان پرهیجان، شما را به صندلی میخکوب می‌کند. کارگردانی پویا و جلوه‌های بصری خیره‌کننده، تجربه‌ای بی‌نظیر خلق کرده‌اند. بازیگران با انرژی تمام نقش‌ها را به تصویر کشیده‌اند. فقط گاهی ریتم تند ممکن است کمی گیج‌کننده باشد.",
        "فیلمی پر از هیجان و صحنه‌های اکشن تماشایی که تا آخر شما را نگه می‌دارد. داستان سرگرم‌کننده و بازیگری قوی، آن را به اثری جذاب تبدیل کرده است. جلوه‌های ویژه بسیار باکیفیت هستند. فقط برخی لحظات ممکن است قابل پیش‌بینی به نظر برسند.",
        "اکشنی پرشور با داستانی مهیج که لحظه‌ای آرامش به شما نمی‌دهد. کارگردانی خلاقانه و موسیقی متن حماسی، حس و حال خاصی به فیلم داده‌اند. بازیگران عملکردی قابل تحسین دارند. فقط برخی دیالوگ‌ها می‌توانستند قوی‌تر باشند."
    ],
    'درام': [
        "این فیلم با داستانی عمیق و احساسی، قلب شما را تسخیر می‌کند. بازیگری بی‌نقص و کارگردانی حساس، آن را به اثری ماندگار تبدیل کرده‌اند. موسیقی متن تأثیرگذار، احساسات را تقویت می‌کند. فقط ریتم کند برخی صحنه‌ها ممکن است صبر شما را بیازماید.",
        "روایتی تکان‌دهنده از زندگی و احساسات انسانی که شما را به فکر فرو می‌برد. فیلم‌برداری زیبا و شخصیت‌پردازی قوی، فیلم را خاص کرده‌اند. داستان عمیق و چندلایه است. فقط پایان ممکن است برای همه رضایت‌بخش نباشد.",
        "داستانی احساسی که شما را به سفری عمیق در روابط انسانی می‌برد. کارگردانی هنرمندانه و بازیگری قوی، لحظات تأثیرگذاری خلق کرده‌اند. موسیقی متن به‌خوبی حس فیلم را منتقل می‌کند. فقط برخی لحظات ممکن است بیش از حد طولانی باشند."
    ],
    'کمدی': [
        "این فیلم با شوخی‌های بامزه و داستان سرگرم‌کننده، شما را به خنده می‌اندازد. بازیگران شیمی فوق‌العاده‌ای دارند و کارگردانی پرانرژی است. دیالوگ‌های هوشمندانه، لحظات شادی خلق می‌کنند. فقط برخی جوک‌ها ممکن است تکراری به نظر برسند.",
        "داستانی سبک و خنده‌دار که حال شما را خوب می‌کند. شخصیت‌پردازی قوی و طنز هوشمندانه، فیلم را جذاب کرده‌اند. بازیگران با مهارت لحظات بامزه‌ای خلق کرده‌اند. فقط ریتم در برخی صحنه‌ها ممکن است افت کند.",
        "کمدی‌ای که با طنز هوشمندانه شما را سرگرم می‌کند. ماجراهای خنده‌دار و شخصیت‌های دوست‌داشتنی، تجربه‌ای شاد ایجاد کرده‌اند. کارگردانی خلاقانه است. فقط برخی شوخی‌ها ممکن است به مذاق همه خوش نیاید."
    ],
    'علمی_تخیلی': [
        "این فیلم با داستانی خلاقانه و جلوه‌های بصری خیره‌کننده، شما را به دنیایی دیگر می‌برد. کارگردانی هوشمندانه و موسیقی متن حماسی، تجربه‌ای بی‌نظیر خلق کرده‌اند. بازیگران نقش‌ها را به‌خوبی ایفا کرده‌اند. فقط برخی مفاهیم ممکن است پیچیده باشند.",
        "جهانی فانتزی که با داستان‌سرایی قوی شما را مجذوب می‌کند. تکنولوژی‌های تخیلی و کارگردانی خلاقانه، فیلم را دیدنی کرده‌اند. بازیگری قوی و داستان پیچیده است. فقط برخی جزئیات ممکن است گنگ باشند.",
        "داستانی علمی‌تخیلی که ذهن شما را به چالش می‌کشد. جلوه‌های ویژه و داستان‌سرایی خلاقانه، تجربه‌ای متفاوت خلق کرده‌اند. شخصیت‌پردازی قوی است. فقط ممکن است برای همه قابل فهم نباشد."
    ],
    'سایر': [
        "فیلمی که با داستان‌سرایی جذاب و کارگردانی قوی، شما را سرگرم می‌کند. بازیگری خوب و روایت روان، تجربه‌ای دلپذیر خلق کرده‌اند. موسیقی متن به‌خوبی حس فیلم را منتقل می‌کند. فقط برخی لحظات ممکن است کند باشند.",
        "داستانی متفاوت که شما را غافلگیر می‌کند. کارگردانی هنرمندانه و بازیگری قوی، فیلم را دیدنی کرده‌اند. داستان چندلایه و جذاب است. فقط برخی صحنه‌ها ممکن است طولانی به نظر برسند.",
        "فیلمی که شما را به دنیایی جدید می‌برد. شخصیت‌هایی که با مشکلات غیرمنتظره روبرو می‌شوند، داستانی هیجان‌انگیز خلق کرده‌اند. کارگردانی خلاقانه است. فقط پایان ممکن است برای همه خوشایند نباشد."
    ]
}

# --- شمارشگر خطاهای API ---
api_errors = {
    'tmdb': 0,
    'omdb': 0
}

# --- توابع کمکی ---
def clean_text(text):
    if not text or text == 'N/A':
        return None
    return text[:300]

def shorten_plot(text, max_sentences=3):
    sentences = [s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟']
    return '. '.join(sentences[:max_sentences]) + ('.' if sentences else '')

def clean_text_for_validation(text):
    """تمیز کردن متن برای اعتبارسنجی"""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[\n\t]', ' ', text)
    return text.strip()

def is_farsi(text):
    farsi_chars = r'[\u0600-\u06FF]'
    return bool(re.search(farsi_chars, text))

def is_valid_plot(text):
    if not text or len(text.split()) < 5:
        return False
    sentences = text.split('. ')
    return len([s for s in sentences if s.strip() and s.strip()[-1] in '.!؟']) >= 1

def is_valid_comment(text):
    """چک کردن معتبر بودن تحلیل: حداقل 4 جمله، 50 کلمه و فارسی بودن"""
    if not text:
        return False
    text = clean_text_for_validation(text)
    if not is_farsi(text):
        logger.warning(f"تحلیل رد شد: متن غیرفارسی - {text}")
        return False
    sentences = [s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟']
    words = len(text.split())
    if len(sentences) < 4:
        logger.warning(f"تحلیل رد شد: کمتر از 4 جمله - {text}")
        return False
    if words < 50:
        logger.warning(f"تحلیل رد شد: کمتر از 50 کلمه - {text}")
        return False
    if text in previous_comments:
        logger.warning(f"تحلیل رد شد: متن تکراری - {text}")
        return False
    return True

def get_fallback_by_genre(options, genres):
    for genre in genres:
        if genre in options:
            available = [opt for opt in options[genre] if opt not in previous_comments]
            if available:
                return random.choice(available)
    available = [opt for genre in options for opt in options[genre] if opt not in previous_comments]
    return random.choice(available) if available else options['سایر'][0]

async def make_api_request(url, retries=5, timeout=15, headers=None):
    # چک کردن کش
    if url in api_cache and (datetime.now() - api_cache[url]['timestamp']).total_seconds() < 3600:
        logger.info(f"استفاده از کش برای {url}")
        return api_cache[url]['data']
    
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=timeout)) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 429:
                        logger.warning(f"خطای 429: Rate Limit، تلاش {attempt + 1}")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if response.status == 401:
                        logger.error(f"خطای 401: کلید API نامعتبر")
                        return None
                    if response.status != 200:
                        logger.error(f"خطای {response.status}: {await response.text()}")
                        return None
                    data = await response.json()
                    # ذخیره در کش
                    api_cache[url] = {'data': data, 'timestamp': datetime.now()}
                    return data
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.error(f"خطای اتصال (تلاش {attempt + 1}): {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except aiohttp.ClientResponseError as e:
            logger.error(f"خطای پاسخ (تلاش {attempt + 1}): {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"خطای غیرمنتظره در درخواست API (تلاش {attempt + 1}): {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
    return None

async def post_api_request(url, data, headers, retries=3, timeout=15):
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=timeout)) as session:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 429:
                        logger.warning(f"خطای 429: Rate Limit، تلاش {attempt + 1}")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if response.status == 401:
                        logger.error(f"خطای 401: کلید API نامعتبر")
                        return None
                    if response.status != 200:
                        logger.error(f"خطای {response.status}: {await response.text()}")
                        return None
                    return await response.json()
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.error(f"خطای اتصال (تلاش {attempt + 1}): {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except aiohttp.ClientResponseError as e:
            logger.error(f"خطای پاسخ (تلاش {attempt + 1}): {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"خطای غیرمنتظره در درخواست API (تلاش {attempt + 1}): {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
    return None

async def get_imdb_score_tmdb(title, genres=None):
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
    
    # چک کردن ژانرها
    is_animation = False
    is_documentary = False
    if genres:
        is_animation = 'انیمیشن' in genres
        is_documentary = 'مستند' in genres
    else:
        details_url = f"https://api.themoviedb.org/3/movie/{movie.get('id')}?api_key={TMDB_API_KEY}&language=en-US"
        details_data = await make_api_request(details_url)
        genres = [GENRE_TRANSLATIONS.get(g['name'], 'سایر') for g in details_data.get('genres', [])]
        is_animation = 'انیمیشن' in genres
        is_documentary = 'مستند' in genres
    
    if is_documentary:
        logger.warning(f"فیلم {title} مستند است، رد شد")
        return None
    
    min_score = 8.0 if is_animation else 6.0
    if imdb_score < min_score:
        logger.warning(f"فیلم {title} امتیاز {imdb_score} دارد، رد شد (حداقل {min_score} لازم است)")
        return None
    api_errors['tmdb'] = 0
    return f"{float(imdb_score):.1f}/10"

async def get_imdb_score_omdb(title, genres=None):
    logger.info(f"دریافت اطلاعات OMDb برای: {title}")
    encoded_title = urllib.parse.quote(title)
    url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_title}&type=movie"
    data = await make_api_request(url)
    if not data or data.get('Response') == 'False':
        logger.warning(f"OMDb هیچ نتیجه‌ای برای {title} نداد: {data.get('Error')}")
        api_errors['omdb'] += 1
        return None
    imdb_score = data.get('imdbRating', 'N/A')
    
    # چک کردن ژانرها
    is_animation = False
    is_documentary = False
    if genres:
        is_animation = 'انیمیشن' in genres
        is_documentary = 'مستند' in genres
    else:
        genres = data.get('Genre', '').split(', ')
        genres = [GENRE_TRANSLATIONS.get(g.strip(), 'سایر') for g in genres]
        is_animation = 'انیمیشن' in genres
        is_documentary = 'مستند' in genres
    
    if is_documentary:
        logger.warning(f"فیلم {title} مستند است، رد شد")
        return None
    
    if imdb_score == 'N/A':
        logger.warning(f"فیلم {title} امتیاز IMDb ندارد، رد شد")
        return None
    
    min_score = 8.0 if is_animation else 6.0
    try:
        score_float = float(imdb_score)
        if score_float < min_score:
            logger.warning(f"فیلم {title} امتیاز {score_float} دارد، رد شد (حداقل {min_score} لازم است)")
            return None
        api_errors['omdb'] = 0
        return f"{score_float:.1f}/10"
    except ValueError:
        logger.warning(f"امتیاز IMDb برای {title} نامعتبر است: {imdb_score}")
        return None

async def check_poster(url):
    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=5)) as session:
            async with session.head(url) as response:
                if response.status != 200:
                    return False
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > 2 * 1024 * 1024:  # 2MB
                    logger.warning(f"پوستر {url} بیش از حد بزرگ است")
                    return False
                return True
    except Exception as e:
        logger.error(f"خطا در چک پوستر {url}: {str(e)}")
        return False

async def save_cache_to_file():
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cached_movies, f, ensure_ascii=False)
        logger.info(f"کش به فایل ذخیره شد: {len(cached_movies)} فیلم")
    except Exception as e:
        logger.error(f"خطا در ذخیره کش به فایل: {str(e)}")
        await send_admin_alert(None, f"❌ خطا در ذخیره کش: {str(e)}. استفاده از کش موقت در حافظه.")

async def load_cache_from_file():
    global cached_movies
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cached_movies = json.load(f)
            logger.info(f"کش از فایل لود شد: {len(cached_movies)} فیلم")
            return True
        logger.info("فایل کش وجود ندارد، ایجاد خواهد شد")
        return False
    except Exception as e:
        logger.error(f"خطا در لود کش از فایل: {str(e)}")
        await send_admin_alert(None, f"❌ خطا در لود کش: {str(e)}. استفاده از کش موقت در حافظه.")
        return False

async def save_posted_movies_to_file():
    try:
        with open(POSTED_MOVIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(posted_movies, f, ensure_ascii=False)
        logger.info(f"لیست فیلم‌های ارسال‌شده ذخیره شد: {len(posted_movies)} فیلم")
    except Exception as e:
        logger.error(f"خطا در ذخیره فیلم‌های ارسال‌شده: {str(e)}")
        await send_admin_alert(None, f"❌ خطا در ذخیره فیلم‌های ارسال‌شده: {str(e)}. استفاده از لیست موقت در حافظه.")

async def load_posted_movies_from_file():
    global posted_movies
    try:
        if os.path.exists(POSTED_MOVIES_FILE):
            with open(POSTED_MOVIES_FILE, 'r', encoding='utf-8') as f:
                posted_movies = json.load(f)
            logger.info(f"لیست فیلم‌های ارسال‌شده لود شد: {len(posted_movies)} فیلم")
            return True
        logger.info("فایل posted_movies وجود ندارد، ایجاد خواهد شد")
        return False
    except Exception as e:
        logger.error(f"خطا در لود فیلم‌های ارسال‌شده: {str(e)}")
        await send_admin_alert(None, f"❌ خطا در لود فیلم‌های ارسال‌شده: {str(e)}. استفاده از لیست موقت در حافظه.")
        return False

async def get_movie_info(title):
    logger.info(f"دریافت اطلاعات برای فیلم: {title}")
    
    # 1. TMDB
    logger.info(f"تلاش با TMDB برای {title}")
    encoded_title = urllib.parse.quote(title)
    search_url_en = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=en-US"
    tmdb_data_en = await make_api_request(search_url_en)
    if tmdb_data_en and tmdb_data_en.get('results'):
        movie = tmdb_data_en['results'][0]
        movie_id = movie.get('id')
        tmdb_title = movie.get('title', title)
        tmdb_poster = f"https://image.tmdb.org/t/p/w185{movie.get('poster_path')}" if movie.get('poster_path') else None
        
        details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
        details_data = await make_api_request(details_url)
        genres = [GENRE_TRANSLATIONS.get(g['name'], 'سایر') for g in details_data.get('genres', [])]
        
        search_url_fa = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=fa-IR"
        tmdb_data_fa = await make_api_request(search_url_fa)
        tmdb_plot = tmdb_data_fa['results'][0].get('overview', '') if tmdb_data_fa.get('results') else ''
        tmdb_year = tmdb_data_fa['results'][0].get('release_date', 'N/A')[:4] if tmdb_data_fa.get('results') else 'N/A'
        
        trailer = None
        videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}&language=en"
        videos_data = await make_api_request(videos_url)
        if videos_data and videos_data.get('results'):
            for video in videos_data['results']:
                if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                    trailer = f"https://www.youtube.com/watch?v={video['key']}"
                    break
        
        imdb_score = await get_imdb_score_tmdb(tmdb_title, genres)
        if not imdb_score:
            logger.warning(f"امتیاز معتبر برای {tmdb_title} یافت نشد")
        else:
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
                'genres': genres[:3],
                'id': movie_id
            }
    
    # 2. OMDb
    logger.info(f"تل       با OMDb برای {title}")
    omdb_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_title}&type=movie"
    omdb_data = await make_api_request(omdb_url)
    if omdb_data and omdb_data.get('Response') == 'True':
        genres = omdb_data.get('Genre', '').split(', ')
        genres = [GENRE_TRANSLATIONS.get(g.strip(), 'سایر') for g in genres]
        imdb_score = await get_imdb_score_omdb(omdb_data.get('Title', title), genres)
        if imdb_score:
            plot = omdb_data.get('Plot', '')
            plot = shorten_plot(plot) if plot and is_farsi(plot) else get_fallback_by_genre(FALLBACK_PLOTS, genres)
            previous_plots.append(plot)
            if len(previous_plots) > 10:
                previous_plots.pop(0)
            omdb_poster = omdb_data.get('Poster', '')
            omdb_poster = omdb_poster if omdb_poster and await check_poster(omdb_poster) else None
            return {
                'title': omdb_data.get('Title', title),
                'year': omdb_data.get('Year', 'N/A'),
                'plot': plot,
                'imdb': imdb_score,
                'trailer': None,
                'poster': omdb_poster,
                'genres': genres[:3],
                'id': omdb_data.get('imdbID')
            }
    
    logger.error(f"هیچ اطلاعات معتبری برای {title} یافت نشد")
    return None

async def fetch_movies_to_cache():
    global cached_movies, last_fetch_time
    logger.info("دریافت فیلم‌های جدید برای کش...")
    
    page = 1
    max_pages = 3
    new_movies = []
    
    while page <= max_pages:
        url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=fa-IR&page={page}"
        data = await make_api_request(url)
        if not data or not data.get('results'):
            logger.error(f"دریافت فیلم‌ها از TMDB ناموفق بود در صفحه {page}")
            break
        
        for movie in data['results']:
            title = movie.get('title')
            genres = [GENRE_TRANSLATIONS.get(g['name'], 'سایر') for g in movie.get('genres', [])]
            if 'مستند' in genres:
                logger.info(f"فیلم {title} مستند است، رد شد")
                continue
            movie_info = await get_movie_info(title)
            if movie_info and movie_info['id'] not in posted_movies:
                new_movies.append(movie_info)
        
        page += 1
    
    if not new_movies:
        logger.warning("هیچ فیلم جدیدی برای کش یافت نشد")
        await send_admin_alert(None, "⚠️ هیچ فیلم جدیدی برای کش یافت نشد. احتمالاً مشکل از APIهای TMDB یا OMDb است یا همه فیلم‌ها قبلاً ارسال شده‌اند.")
        return
    
    cached_movies = new_movies
    last_fetch_time = datetime.now()
    await save_cache_to_file()
    logger.info(f"کش با موفقیت آپدیت شد در {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: {len(cached_movies)} فیلم")

async def get_random_movie():
    global cached_movies, last_fetch_time
    await load_cache_from_file()
    await load_posted_movies_from_file()
    
    if not cached_movies or (datetime.now() - last_fetch_time).seconds > FETCH_INTERVAL:
        logger.info("کش خالی یا قدیمی، آپدیت کش...")
        await fetch_movies_to_cache()
    
    if not cached_movies:
        logger.error("کش فیلم‌ها خالی است، ارسال پست لغو شد")
        await send_admin_alert(None, "⚠️ کش فیلم‌ها خالی است. لطفاً APIهای TMDB و OMDb را بررسی کنید یا کش را به‌صورت دستی آپدیت کنید.")
        return None
    
    available_movies = [m for m in cached_movies if m['id'] not in posted_movies]
    if not available_movies:
        logger.warning("هیچ فیلم جدیدی در کش نیست، ارسال پست لغو شد")
        await send_admin_alert(None, "⚠️ هیچ فیلم جدیدی در کش نیست. همه فیلم‌های موجود قبلاً ارسال شده‌اند یا مستند هستند.")
        return None
    
    for movie in available_movies:
        if 'مستند' in movie['genres']:
            logger.warning(f"فیلم {movie['title']} مستند است، رد شد")
            continue
        posted_movies.append(movie['id'])
        await save_posted_movies_to_file()
        return movie
    
    logger.warning("هیچ فیلم غیرمستندی یافت نشد، ارسال پست لغو شد")
    await send_admin_alert(None, "⚠️ هیچ فیلم غیرمستندی در کش یافت نشد. لطفاً کش را بررسی کنید.")
    return None

async def generate_comment(genres):
    global fallback_count
    logger.info("تولید تحلیل...")
    comment = None
    
    # Gemini
    if api_availability['gemini']:
        logger.info("تلاش با Gemini")
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = "یک تحلیل جذاب و حرفه‌ای به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، در حداقل 4 جمله کامل (هر جمله با نقطه پایان یابد) و حداقل 50 کلمه. لحن سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد."
            response = await model.generate_content_async(prompt)
            text = response.text.strip()
            if is_valid_comment(text):
                comment = text
                previous_comments.append(comment)
                if len(previous_comments) > 10:
                    previous_comments.pop(0)
                api_availability['gemini'] = True
                api_downtime['gemini'] = None
                fallback_count = 0
                return comment
            else:
                logger.warning(f"تحلیل Gemini رد شد: {text}")
        except google_exceptions.GoogleAPIError as e:
            logger.error(f"خطا در Gemini API: {str(e)}")
            api_availability['gemini'] = False
            if api_downtime['gemini'] is None:
                api_downtime['gemini'] = datetime.now()
            await send_admin_alert(None, f"❌ خطا در Gemini: {str(e)}.")
        except Exception as e:
            logger.error(f"خطای غیرمنتظره در Gemini: {str(e)}")
            api_availability['gemini'] = False
            if api_downtime['gemini'] is None:
                api_downtime['gemini'] = datetime.now()
            await send_admin_alert(None, f"❌ خطا در Gemini: {str(e)}.")
    
    # Groq
    if api_availability['groq']:
        logger.info("تلاش با Groq")
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
                    {"role": "user", "content": "یک تحلیل جذاب و حرفه‌ای به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، در حداقل 4 جمله کامل (هر جمله با نقطه پایان یابد) و حداقل 50 کلمه. لحن سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد. فقط به فارسی بنویس و از کلمات انگلیسی استفاده نکن."}
                ],
                "max_tokens": 250,
                "temperature": 0.7
            }
            response = await post_api_request(url, data, headers, retries=3)
            text = response['choices'][0]['message']['content'].strip() if response and response.get('choices') else ""
            if is_valid_comment(text):
                comment = text
                previous_comments.append(comment)
                if len(previous_comments) > 10:
                    previous_comments.pop(0)
                api_availability['groq'] = True
                api_downtime['groq'] = None
                fallback_count = 0
                return comment
            else:
                logger.warning(f"تحلیل Groq رد شد: {text}")
        except Exception as e:
            logger.error(f"خطا در Groq API: {str(e)}")
            api_availability['groq'] = False
            if api_downtime['groq'] is None:
                api_downtime['groq'] = datetime.now()
            await send_admin_alert(None, f"❌ خطا در Groq: {str(e)}.")
    
    # Open AI
    if api_availability['openai']:
        logger.info("تلاش با Open AI")
        try:
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Write in Persian."},
                    {"role": "user", "content": "یک تحلیل جذاب و حرفه‌ای به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، در حداقل 4 جمله کامل (هر جمله با نقطه پایان یابد) و حداقل 50 کلمه. لحن سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد. فقط به فارسی بنویس و از کلمات انگلیسی استفاده نکن."}
                ],
                max_tokens=250,
                temperature=0.7
            )
            text = response.choices[0].message.content.strip()
            if is_valid_comment(text):
                comment = text
                previous_comments.append(comment)
                if len(previous_comments) > 10:
                    previous_comments.pop(0)
                api_availability['openai'] = True
                api_downtime['openai'] = None
                fallback_count = 0
                return comment
            else:
                logger.warning(f"تحلیل Open AI رد شد: {text}")
        except Exception as e:
            logger.error(f"خطا در Open AI API: {str(e)}")
            api_availability['openai'] = False
            if api_downtime['openai'] is None:
                api_downtime['openai'] = datetime.now()
            await send_admin_alert(None, f"❌ خطا در Open AI: {str(e)}.")
    
    # فال‌بک
    if not comment:
        logger.warning("هیچ تحلیلگری در دسترس نیست، استفاده از فال‌بک")
        comment = get_fallback_by_genre(FALLBACK_COMMENTS, genres)
        fallback_count += 1
        if fallback_count >= 5:
            await send_admin_alert(None, "⚠️ هشدار: ۵ پست متوالی با فال‌بک ارسال شد. هوش مصنوعی‌ها در دسترس نیستند.")
            logger.warning("۵ پست متوالی با فال‌بک ارسال شد")
            fallback_count = 0
    
    previous_comments.append(comment)
    if len(previous_comments) > 10:
        previous_comments.pop(0)
    return comment

async def check_api_downtime(context: ContextTypes.DEFAULT_TYPE):
    logger.info("چک کردن زمان قطعی APIها...")
    for api, downtime in api_downtime.items():
        if downtime and (datetime.now() - downtime).total_seconds() >= 259200:  # 3 روز
            await send_admin_alert(context, f"⚠️ هشدار: API {api} برای بیش از 3 روز در دسترس نیست. لطفاً بررسی کنید.")
            logger.warning(f"API {api} برای بیش از 3 روز قطع است")

async def format_movie_post(movie):
    comment = await generate_comment(movie['genres'])
    genres = '، '.join(movie['genres'])
    trailer = f"\n📽️ <a href='{movie['trailer']}'>تریلر</a>" if movie['trailer'] else ""
    return (
        f"🎬 <b>{movie['title']}</b> ({movie['year']})\n"
        f"📌 ژانر: {genres}\n"
        f"⭐️ امتیاز IMDb: {movie['imdb']}\n\n"
        f"📖 خلاصه داستان:\n{movie['plot']}\n\n"
        f"💬 حرف ما:\n{comment}\n"
        f"{trailer}"
    )

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    logger.info("شروع پست خودکار...")
    try:
        if not bot_enabled:
            logger.info("پست خودکار کنسل شد: ربات غیرفعال است")
            return
        movie = await get_random_movie()
        if not movie:
            logger.error("هیچ فیلمی برای پست کردن یافت نشد، پست لغو شد")
            return
        
        logger.info(f"فیلم انتخاب شد: {movie['title']}")
        caption = await format_movie_post(movie)  # دریافت کپشن
        if movie['poster']:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=movie['poster'],
                caption=caption,
                parse_mode='HTML',
                disable_notification=True
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=caption,
                parse_mode='HTML',
                disable_notification=True
            )
        logger.info(f"پست خودکار برای {movie['title']} ارسال شد")
    except Exception as e:
        logger.error(f"خطا در ارسال پست خودکار: {e}")
        await send_admin_alert(context, f"❌ خطای پست خودکار: {str(e)}")

async def auto_fetch_movies(context: ContextTypes.DEFAULT_TYPE):
    logger.info("شروع آپدیت خودکار کش...")
    await fetch_movies_to_cache()

async def send_admin_alert(context, message):
    if context:
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=message)
        except Exception as e:
            logger.error(f"خطا در ارسال هشدار به ادمین: {e}")
    else:
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={'chat_id': ADMIN_ID, 'text': message}
                )
        except Exception as e:
            logger.error(f"خطا در ارسال هشدار به ادمین (بدون context): {e}")

async def run_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = []
    
    # تست TMDB
    tmdb_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=fa-IR&page=1"
    tmdb_data = await make_api_request(tmdb_url)
    tmdb_status = "✅ TMDB اوکی" if tmdb_data and tmdb_data.get('results') else f"❌ TMDB خطا: {tmdb_data}"
    results.append(tmdb_status)
    
    # تست OMDb
    omdb_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t=Inception&type=movie"
    omdb_data = await make_api_request(omdb_url)
    omdb_status = "✅ OMDb اوکی" if omdb_data and omdb_data.get('Response') == 'True' else f"❌ OMDb خطا: {omdb_data.get('Error', 'نامشخص')}"
    results.append(omdb_status)
    
    # تست JobQueue
    job_queue = context.job_queue
    job_queue_status = "✅ JobQueue فعال" if job_queue else "❌ JobQueue غیرفعال"
    results.append(job_queue_status)
    
    # تست Gemini
    gemini_status = "❌ Gemini غیرفعال"  # پیش‌فرض
    if api_availability['gemini']:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = "تست: یک جمله به فارسی بنویس."
            response = await model.generate_content_async(prompt)
            text = response.text.strip()
            gemini_status = "✅ Gemini اوکی" if text and is_farsi(text) else "❌ Gemini خطا: پاسخ نامعتبر"
        except Exception as e:
            logger.error(f"خطا در تست Gemini: {str(e)}")
            api_availability['gemini'] = False
            gemini_status = f"❌ Gemini خطا: {str(e)}"
    results.append(gemini_status)
    
    # تست Groq
    groq_status = "❌ Groq غیرفعال"  # پیش‌فرض
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
                "temperature": 0.7
            }
            response = await post_api_request(url, data, headers, retries=3)
            text = response['choices'][0]['message']['content'].strip() if response and response.get('choices') else ""
            groq_status = "✅ Groq اوکی" if text and is_farsi(text) else f"❌ Groq خطا: پاسخ نامعتبر - متن دریافتی: {text}"
        except Exception as e:
            logger.error(f"خطا در تست Groq: {str(e)}")
            api_availability['groq'] = False
            groq_status = f"❌ Groq خطا: {str(e)}"
    results.append(groq_status)
    
    # تست Open AI
    openai_status = "❌ Open AI غیرفعال"  # پیش‌فرض
    if api_availability['openai']:
        try:
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Write in Persian."},
                    {"role": "user", "content": "تست: یک جمله به فارسی بنویس."}
                ],
                max_tokens=50,
                temperature=0.7
            )
            text = response.choices[0].message.content.strip()
            openai_status = "✅ Open AI اوکی" if text and is_farsi(text) else "❌ Open AI خطا: پاسخ نامعتبر"
        except Exception as e:
            logger.error(f"خطا در تست Open AI: {str(e)}")
            api_availability['openai'] = False
            openai_status = f"❌ Open AI خطا: {str(e)}"
    results.append(openai_status)
    
    logger.info(f"نتایج تست فنی: {results}")
    return "\n".join(results)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("دسترسی غیرمجاز! فقط ادمین می‌تواند از این بات استفاده کند.")
        return
    
    keyboard = [
        [InlineKeyboardButton("تست‌ها", callback_data='tests_menu')],
        [InlineKeyboardButton("دریافت فیلم‌ها", callback_data='fetch_movies')],
        [InlineKeyboardButton("ارسال فوری", callback_data='post_now')],
        [InlineKeyboardButton("نمایش فیلم‌ها", callback_data='show_movies')],
        [InlineKeyboardButton("فعال/غیرفعال کردن ربات", callback_data='toggle_bot')],
        [InlineKeyboardButton("ریست Webhook", callback_data='reset_webhook')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("منوی ادمین:", reply_markup=reply_markup)

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("تست‌ها", callback_data='tests_menu')],
        [InlineKeyboardButton("دریافت فیلم‌ها", callback_data='fetch_movies')],
        [InlineKeyboardButton("ارسال فوری", callback_data='post_now')],
        [InlineKeyboardButton("نمایش فیلم‌ها", callback_data='show_movies')],
        [InlineKeyboardButton("فعال/غیرفعال کردن ربات", callback_data='toggle_bot')],
        [InlineKeyboardButton("ریست Webhook", callback_data='reset_webhook')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("منوی ادمین:", reply_markup=reply_markup)

async def tests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("دسترسی فنی", callback_data='test_all')],
        [InlineKeyboardButton("ارسال به کانال", callback_data='test_channel')],
        [InlineKeyboardButton("بازگشت", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("منوی تست‌ها:", reply_markup=reply_markup)

async def test_all_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    results = await run_tests(update, context)
    keyboard = [[InlineKeyboardButton("بازگشت", callback_data='tests_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"نتایج تست فنی:\n{results}", reply_markup=reply_markup)

async def test_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text="تست ارسال به کانال موفق بود!")
        result = "✅ ارسال به کانال اوکی"
    except Exception as e:
        result = f"❌ خطا در ارسال به کانال: {str(e)}"
        await send_admin_alert(context, f"❌ خطا در تست کانال: {str(e)}")
    keyboard = [[InlineKeyboardButton("بازگشت", callback_data='tests_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(result, reply_markup=reply_markup)

async def fetch_movies_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await fetch_movies_to_cache()
    keyboard = [[InlineKeyboardButton("بازگشت", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"کش فیلم‌ها آپدیت شد: {len(cached_movies)} فیلم", reply_markup=reply_markup)

async def post_now_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await auto_post(context)
    keyboard = [[InlineKeyboardButton("بازگشت", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("پست فوری ارسال شد", reply_markup=reply_markup)

async def show_movies_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await load_cache_from_file()
    if not cached_movies:
        text = "هیچ فیلمی در کش موجود نیست."
    else:
        text = "\n".join([f"{m['title']} ({m['year']})" for m in cached_movies[:10]])
        if len(cached_movies) > 10:
            text += "\n... و بیشتر"
    keyboard = [[InlineKeyboardButton("بازگشت", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"فیلم‌های کش:\n{text}", reply_markup=reply_markup)

async def toggle_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_enabled
    query = update.callback_query
    await query.answer()
    bot_enabled = not bot_enabled
    status = "فعال" if bot_enabled else "غیرفعال"
    keyboard = [[InlineKeyboardButton("بازگشت", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"ربات {status} شد", reply_markup=reply_markup)

async def reset_webhook_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
                json={"drop_pending_updates": True}
            )
        result = "✅ Webhook ریست شد"
    except Exception as e:
        result = f"❌ خطا در ریست Webhook: {str(e)}"
        await send_admin_alert(context, f"❌ خطا در ریست Webhook: {str(e)}")
    keyboard = [[InlineKeyboardButton("بازگشت", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(result, reply_markup=reply_markup)

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("دسترسی غیرمجاز!")
        return
    debug_info = (
        f"وضعیت ربات: {'فعال' if bot_enabled else 'غیرفعال'}\n"
        f"تعداد فیلم‌ها در کش: {len(cached_movies)}\n"
        f"فیلم‌های ارسال‌شده: {len(posted_movies)}\n"
        f"آخرین آپدیت کش: {last_fetch_time}\n"
        f"وضعیت APIها:\n"
        f" - Gemini: {'فعال' if api_availability['gemini'] else 'غیرفعال'}\n"
        f" - Groq: {'فعال' if api_availability['groq'] else 'غیرفعال'}\n"
        f" - Open AI: {'فعال' if api_availability['openai'] else 'غیرفعال'}\n"
        f"خطاهای API:\n"
        f" - TMDB: {api_errors['tmdb']}\n"
        f" - OMDb: {api_errors['omdb']}"
    )
    await update.message.reply_text(debug_info)

async def health_check(request):
    return web.Response(text="OK")

async def run_web():
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"سرور وب روی پورت {PORT} فعال شد")
    return runner

async def run_bot():
    global bot_app
    logger.info("شروع راه‌اندازی بات تلگرام...")
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("Application ساخته شد")
    except Exception as e:
        logger.error(f"خطا در ساخت Application: {str(e)}")
        await send_admin_alert(None, f"❌ خطا در ساخت بات: {str(e)}")
        raise
    
    # اضافه کردن handlerها
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("resetwebhook", reset_webhook_handler))
    
    app.add_handler(CallbackQueryHandler(back_to_main, pattern='^back_to_main$'))
    app.add_handler(CallbackQueryHandler(tests_menu, pattern='^tests_menu$'))
    app.add_handler(CallbackQueryHandler(fetch_movies_handler, pattern='^fetch_movies$'))
    app.add_handler(CallbackQueryHandler(post_now_handler, pattern='^post_now$'))
    app.add_handler(CallbackQueryHandler(test_all_handler, pattern='^test_all$'))
    app.add_handler(CallbackQueryHandler(test_channel_handler, pattern='^test_channel$'))
    app.add_handler(CallbackQueryHandler(show_movies_handler, pattern='^show_movies$'))
    app.add_handler(CallbackQueryHandler(toggle_bot_handler, pattern='^toggle_bot$'))
    app.add_handler(CallbackQueryHandler(reset_webhook_handler, pattern='^reset_webhook$'))
    
    job_queue = app.job_queue
    if job_queue:
        logger.info("JobQueue فعال شد")
        job_queue.run_repeating(auto_post, interval=POST_INTERVAL, first=10)
        job_queue.run_repeating(auto_fetch_movies, interval=FETCH_INTERVAL, first=60)
        job_queue.run_repeating(check_api_downtime, interval=86400, first=3600)
    else:
        logger.error("JobQueue فعال نشد، ربات متوقف می‌شود")
        await send_admin_alert(None, "❌ خطا: JobQueue فعال نشد. لطفاً ربات را بررسی کنید.")
        global bot_enabled
        bot_enabled = False
        raise Exception("JobQueue غیرفعال است")
    
    bot_app = app
    await app.initialize()
    await app.start()
    logger.info("بات تلگرام با موفقیت راه‌اندازی شد")
    return app

async def main():
    logger.info("شروع برنامه...")
    await init_openai_client()
    
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
                json={"drop_pending_updates": True}
            )
        logger.info("Webhook ریست شد")
    except Exception as e:
        logger.error(f"خطا در ریست Webhook: {str(e)}")
        await send_admin_alert(None, f"❌ خطا در ریست Webhook: {str(e)}")
    
    await load_cache_from_file()
    await load_posted_movies_from_file()
    
    web_runner = await run_web()
    
    try:
        bot_app = await run_bot()
        await bot_app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            close_loop=False,
            stop_signals=[],
            drop_pending_updates=True
        )
    except Exception as e:
        logger.error(f"خطا در اجرای بات: {str(e)}")
        await send_admin_alert(None, f"❌ خطا در اجرای بات: {str(e)}")
    finally:
        if bot_app and bot_app.running:
            await bot_app.updater.stop()
            await bot_app.stop()
            await bot_app.shutdown()
        await web_runner.cleanup()
        if client:
            await client.close()

if __name__ == '__main__':
    asyncio.run(main())
