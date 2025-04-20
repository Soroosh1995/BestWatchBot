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
FETCH_INTERVAL = int(os.getenv('FETCH_INTERVAL', 86400))

# تنظیم Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# تنظیم Open AI
client = None

async def init_openai_client():
    global client
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# --- وضعیت دسترسی APIها ---
api_availability = {
    'gemini': True,
    'groq': True,
    'openai': True
}

# --- کش و متغیرهای سراسری ---
cached_movies = []
posted_movies = []
last_fetch_time = datetime.now() - timedelta(days=1)
previous_plots = []
previous_comments = []
bot_enabled = True
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

# --- فال‌بک‌های گسترده‌تر ---
FALLBACK_MOVIES = [
    {
        'title': 'Inception',
        'year': '2010',
        'plot': 'دزدی که اسرار شرکت‌ها را با فناوری رویا می‌دزدد، باید ایده‌ای در ذهن یک مدیر بکارد. گذشته غم‌انگیز او ممکن است پروژه را به فاجعه بکشاند.',
        'imdb': '8.8/10',
        'trailer': 'https://www.youtube.com/watch?v=YoHD9XEInc0',
        'poster': 'https://m.media-amazon.com/images/M/MV5BMjAxMzY3NjcxNF5BMl5BanBnXkFtZTcwNTI5OTM0Mw@@._V1_SX300.jpg',
        'genres': ['علمی_تخیلی', 'هیجان_انگیز']
    },
    {
        'title': 'The Matrix',
        'year': '1999',
        'plot': 'هکری که دنیایی شبیه‌سازی‌شده را کشف می‌کند، باید علیه ماشین‌هایی که بشریت را زندانی کرده‌اند بجنگد.',
        'imdb': '8.7/10',
        'trailer': 'https://www.youtube.com/watch?v=m8e-FF8MsWU',
        'poster': 'https://m.media-amazon.com/images/M/MV5BNzQzOTk3OTAtNDQ0Zi00ZTVkLWI0MTEtMDllZjNkYzNjNTc4L2ltYWdlXkEyXkFqcGdeQXVyNjU0OTQ0OTY@._V1_SX300.jpg',
        'genres': ['علمی_تخیلی', 'اکشن']
    },
    {
        'title': 'The Shawshank Redemption',
        'year': '1994',
        'plot': 'مردی بی‌گناه به زندان می‌افتد و دوستی عمیقی با یک زندانی دیگر شکل می‌دهد. آیا امیدی برای آزادی وجود دارد؟',
        'imdb': '9.3/10',
        'trailer': 'https://www.youtube.com/watch?v=6hB3S9bIaco',
        'poster': 'https://m.media-amazon.com/images/M/MV5BMDFkYTc0MGEtZmNhMC00ZDIzLWFmNTEtODM1ZmRlYWMwMWFmXkEyXkFqcGdeQXVyMTMxODk2OTU@._V1_SX300.jpg',
        'genres': ['درام']
    },
    {
        'title': 'Interstellar',
        'year': '2014',
        'plot': 'گروهی از فضانوردان برای یافتن خانه‌ای جدید برای بشریت به سفری بین‌ستاره‌ای می‌روند. آیا موفق خواهند شد؟',
        'imdb': '8.6/10',
        'trailer': 'https://www.youtube.com/watch?v=zSWdZVtXT7E',
        'poster': 'https://m.media-amazon.com/images/M/MV5BZjdkOTU3MDktN2IxOS00OGYyLWFhMjktYzk2ODVhZmM0YzkxXkEyXkFqcGdeQXVyNjU0OTQ0OTY@._V1_SX300.jpg',
        'genres': ['علمی_تخیلی', 'درام']
    },
    {
        'title': 'Fight Club',
        'year': '1999',
        'plot': 'مردی ناامید باشگاهی مخفی برای مبارزه راه می‌اندازد، اما همه‌چیز از کنترل خارج می‌شود.',
        'imdb': '8.8/10',
        'trailer': 'https://www.youtube.com/watch?v=SUXWAEX2jlg',
        'poster': 'https://m.media-amazon.com/images/M/MV5BMmEzNTkxYjQtZTc0MC00YTVjLTg5ZTEtZWMwOWVlYzY0NWIwXkEyXkFqcGdeQXVyNzkwMjQ5NzM@._V1_SX300.jpg',
        'genres': ['درام', 'هیجان_انگیز']
    }
]

FALLBACK_PLOTS = {
    'اکشن': [
        "ماجراجویی پرهیجانی که قهرمان با دشمنان قدرتمند روبرو می‌شود. نبردهای نفس‌گیر شما را میخکوب می‌کند. آیا او می‌تواند جهان را نجات دهد؟",
        "داستانی پر از تعقیب و گریز و انفجارهای مهیج. قهرمانی که برای عدالت می‌جنگد. آیا او پیروز خواهد شد؟",
        "مبارزه‌ای حماسی برای نجات بشریت. صحنه‌های اکشن خیره‌کننده و داستانی پرتعلیق. آیا پایان خوشی در انتظار است؟",
    ],
    'درام': [
        "داستانی عمیق از روابط انسانی و انتخاب‌های سخت. زندگی شخصیتی پیچیده که قلب شما را لمس می‌کند. آیا او راه خود را پیدا خواهد کرد؟",
        "روایتی احساسی از چالش‌های زندگی و عشق. تصمیم‌هایی که آینده را تغییر می‌دهند. آیا پایان خوشی در انتظار است؟",
        "سفری احساسی در دل مشکلات زندگی. شخصیت‌هایی که با شجاعت مبارزه می‌کنند. آیا امید پیروز می‌شود؟",
    ],
    'کمدی': [
        "ماجراهای خنده‌داری که زندگی را زیرورو می‌کنند. گروهی از دوستان که در موقعیت‌های عجیب گیر می‌افتند. آیا از این مخمصه خلاص می‌شوند؟",
        "داستانی پر از شوخی و موقعیت‌های بامزه. شخصیت‌هایی که شما را به خنده می‌اندازند. آیا همه‌چیز به خیر می‌گذرد؟",
        "کمدی‌ای که با طنز هوشمندانه شما را سرگرم می‌کند. ماجراهایی که خنده را به لب‌هایتان می‌آورد. آیا پایان شادی در انتظار است؟",
    ],
    'علمی_تخیلی': [
        "جهانی در آینده که تکنولوژی همه‌چیز را تغییر داده. ماجراجویی‌ای برای کشف حقیقت پشت یک راز بزرگ. آیا بشریت نجات پیدا می‌کند؟",
        "داستانی از سفر در زمان و فضا. اکتشافاتی که جهان را دگرگون می‌کنند. آیا حقیقت آشکار خواهد شد؟",
        "ماجراجویی‌ای در فضایی ناشناخته. فناوری‌های عجیب و داستانی پیچیده. آیا قهرمانان موفق می‌شوند؟",
    ],
    'سایر': [
        "داستانی جذاب که شما را به سفری غیرمنتظره می‌برد. شخصیت‌هایی که با چالش‌های بزرگ روبرو می‌شوند. آیا پایان خوشی در انتظار است؟",
        "روایتی متفاوت که شما را غافلگیر می‌کند. ماجراهایی که قلب و ذهن را درگیر می‌کنند. آیا همه‌چیز درست می‌شود؟",
    ]
}

FALLBACK_COMMENTS = {
    'اکشن': [
        "این فیلم با صحنه‌های اکشن نفس‌گیر و داستان پرهیجان، شما را به صندلی میخکوب می‌کند. کارگردانی پویا و جلوه‌های بصری خیره‌کننده از نقاط قوت آن است. فقط گاهی ریتم تند ممکن است کمی گیج‌کننده باشد.",
        "فیلمی پر از هیجان و صحنه‌های اکشن تماشایی. داستان سرگرم‌کننده و بازیگری قوی، آن را جذاب کرده است. فقط برخی لحظات ممکن است قابل پیش‌بینی باشند.",
        "اکشنی پرشور با داستانی مهیج که شما را تا آخر نگه می‌دارد. جلوه‌های ویژه عالی هستند. فقط برخی دیالوگ‌ها می‌توانستند قوی‌تر باشند.",
    ],
    'درام': [
        "این فیلم با داستانی عمیق و احساسی، قلب شما را تسخیر می‌کند. بازیگری بی‌نقص و کارگردانی حساس، آن را به اثری ماندگار تبدیل کرده‌اند. فقط ریتم کند برخی صحنه‌ها ممکن است صبر شما را بیازماید.",
        "روایتی تکان‌دهنده از زندگی و احساسات انسانی. فیلم‌برداری زیبا و موسیقی متن تأثیرگذار، آن را خاص کرده‌اند. فقط پایان ممکن است برای همه رضایت‌بخش نباشد.",
        "داستانی احساسی که شما را به فکر فرو می‌برد. شخصیت‌پردازی قوی و کارگردانی هنرمندانه از نقاط قوت آن است. فقط برخی لحظات ممکن است بیش از حد طولانی باشند.",
    ],
    'کمدی': [
        "این فیلم با شوخی‌های بامزه و داستان سرگرم‌کننده، شما را به خنده می‌اندازد. بازیگران شیمی فوق‌العاده‌ای دارند و کارگردانی پرانرژی است. فقط برخی جوک‌ها ممکن است تکراری به نظر برسند.",
        "داستانی سبک و خنده‌دار که حال شما را خوب می‌کند. شخصیت‌پردازی قوی و دیالوگ‌های هوشمندانه از نقاط قوت آن است. فقط ریتم در برخی صحنه‌ها افت می‌کند.",
        "کمدی‌ای که با طنز هوشمندانه شما را سرگرم می‌کند. بازیگران فوق‌العاده و داستان بامزه از نقاط قوت آن است. فقط برخی شوخی‌ها ممکن است به مذاق همه خوش نیاید.",
    ],
    'علمی_تخیلی': [
        "این فیلم با داستانی خلاقانه و جلوه‌های بصری خیره‌کننده، شما را به دنیایی دیگر می‌برد. کارگردانی هوشمندانه و موسیقی متن حماسی از نقاط قوت آن است. فقط برخی مفاهیم ممکن است پیچیده باشند.",
        "جهانی فانتزی که با داستان‌سرایی قوی شما را مجذوب می‌کند. تکنولوژی‌های تخیلی و کارگردانی خلاقانه، آن را دیدنی کرده‌اند. فقط برخی جزئیات ممکن است گنگ باشند.",
        "داستانی علمی‌تخیلی که ذهن شما را به چالش می‌کشد. جلوه‌های ویژه و داستان‌سرایی خلاقانه از نقاط قوت آن است. فقط ممکن است برای همه قابل فهم نباشد.",
    ],
    'سایر': [
        "فیلمی که با داستان‌سرایی جذاب و کارگردانی قوی، شما را سرگرم می‌کند. بازیگری خوب و روایت روان از نقاط قوت آن است. فقط برخی لحظات ممکن است کند باشند.",
        "داستانی متفاوت که شما را غافلگیر می‌کند. کارگردانی هنرمندانه و بازیگری قوی، آن را دیدنی کرده‌اند. فقط برخی صحنه‌ها ممکن است طولانی به نظر برسند.",
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
    """تمیز کردن متن برای اعتبارسنجی: حذف فاصله‌های اضافی و کاراکترهای غیرضروری"""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)  # جایگزینی فاصله‌های اضافی با یک فاصله
    text = re.sub(r'[\n\t]', ' ', text)  # حذف خط جدید و تب
    text = text.strip()
    return text

def is_farsi(text):
    farsi_chars = r'[\u0600-\u06FF]'
    return bool(re.search(farsi_chars, text))

def is_valid_plot(text):
    if not text or len(text.split()) < 5:
        return False
    sentences = text.split('. ')
    return len([s for s in sentences if s.strip() and s.strip()[-1] in '.!؟']) >= 1

def is_valid_comment(text):
    """چک کردن معتبر بودن تحلیل: حداقل 3 جمله و فارسی بودن"""
    if not text:
        return False
    text = clean_text_for_validation(text)
    if not is_farsi(text):
        logger.warning(f"تحلیل رد شد: متن غیرفارسی - {text}")
        return False
    sentences = [s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟']
    if len(sentences) < 3:
        logger.warning(f"تحلیل رد شد: کمتر از 3 جمله - {text}")
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
    
    # چک کردن ژانر انیمیشن
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

async def get_imdb_score_omdb(title, genres=None):
    logger.info(f"دریافت اطلاعات OMDb برای: {title}")
    encoded_title = urllib.parse.quote(title)
    url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_title}&type=movie"
    data = await make_api_request(url)
    if not data or data.get('Response') == 'False':
        logger.warning(f"OMDb هیچ نتیجه‌ای برای {title} نداد: {data.get('Error')}")
        api_errors['omdb'] += 1
        return None
    imdb_score = data.get('imdbRating', '0')
    
    # چک کردن ژانر انیمیشن
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

async def check_poster(url):
    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=5)) as session:
            async with session.head(url) as response:
                if response.status != 200:
                    return False
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > 5 * 1024 * 1024:  # 5MB
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
        tmdb_poster = f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else None
        
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
                'genres': genres[:3]
            }
    
    # 2. OMDb
    logger.info(f"تلاش با OMDb برای {title}")
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
            return {
                'title': omdb_data.get('Title', title),
                'year': omdb_data.get('Year', 'N/A'),
                'plot': plot,
                'imdb': imdb_score,
                'trailer': None,
                'poster': omdb_data.get('Poster', None),
                'genres': genres[:3]
            }
    
    logger.error(f"هیچ API برای {title} جواب نداد")
    if api_errors['tmdb'] > 5 or api_errors['omdb'] > 5:
        await send_admin_alert(None, f"⚠️ هشدار: APIهای متعدد ({api_errors}) خطا دارند. لطفاً کلیدهای TMDB و OMDb را بررسی کنید.")
    return random.choice(FALLBACK_MOVIES)

async def generate_comment(genres):
    logger.info("تولید تحلیل...")

    # 1. Gemini
    if api_availability['gemini']:
        logger.info("تلاش با Gemini")
        try:
            async with asyncio.timeout(15):
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = "یک تحلیل کوتاه و جذاب به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، در 3 جمله کامل (هر جمله با نقطه پایان یابد). لحن حرفه‌ای و سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد."
                response = await model.generate_content_async(prompt)
                text = clean_text_for_validation(response.text.strip())
                if is_valid_comment(text):
                    previous_comments.append(text)
                    if len(previous_comments) > 10:
                        previous_comments.pop(0)
                    logger.info("تحلیل Gemini با موفقیت دریافت شد")
                    return '. '.join([s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟'][:3]) + '.'
                logger.warning(f"تحلیل Gemini نامعتبر: {text}")
        except google_exceptions.ResourceExhausted:
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
            async with asyncio.timeout(15):
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": "mistral-saba-24b",
                    "messages": [
                        {"role": "system", "content": "You are a professional film critic writing in Persian."},
                        {"role": "user", "content": "یک تحلیل کوتاه و جذاب به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، در 3 جمله کامل (هر جمله با نقطه پایان یابد). لحن حرفه‌ای و سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد. فقط به فارسی بنویس و از کلمات انگلیسی استفاده نکن."}
                    ],
                    "max_tokens": 150,
                    "temperature": 0.7
                }
                response = await post_api_request(url, data, headers, retries=3)
                if response and response.get('choices'):
                    text = clean_text_for_validation(response['choices'][0]['message']['content'].strip())
                    if is_valid_comment(text):
                        previous_comments.append(text)
                        if len(previous_comments) > 10:
                            previous_comments.pop(0)
                        logger.info("تحلیل Groq با موفقیت دریافت شد")
                        return '. '.join([s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟'][:3]) + '.'
                    logger.warning(f"تحلیل Groq نامعتبر: {text}")
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

    # 3. Open AI
    if api_availability['openai']:
        logger.info("تلاش با Open AI")
        try:
            async with asyncio.timeout(15):
                response = await client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a professional film critic writing in Persian."},
                        {"role": "user", "content": "یک تحلیل کوتاه و جذاب به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، در 3 جمله کامل (هر جمله با نقطه پایان یابد). لحن حرفه‌ای و سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد. فقط به فارسی بنویس و از کلمات انگلیسی استفاده نکن."}
                    ],
                    max_tokens=150,
                    temperature=0.7
                )
                text = clean_text_for_validation(response.choices[0].message.content.strip())
                if is_valid_comment(text):
                    previous_comments.append(text)
                    if len(previous_comments) > 10:
                        previous_comments.pop(0)
                    logger.info("تحلیل Open AI با موفقیت دریافت شد")
                    return '. '.join([s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟'][:3]) + '.'
                logger.warning(f"تحلیل Open AI نامعتبر: {text}")
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.error(f"خطای اتصال Open AI: {str(e)}")
            api_availability['openai'] = False
            await send_admin_alert(None, f"❌ مشکل اتصال به Open AI: {str(e)}.")
        except Exception as e:
            logger.error(f"خطا در Open AI API: {str(e)}")
            api_availability['openai'] = False
            await send_admin_alert(None, f"❌ خطا در Open AI: {str(e)}.")

    # 4. فال‌بک
    logger.warning("هیچ تحلیلگری در دسترس نیست، استفاده از فال‌بک")
    comment = get_fallback_by_genre(FALLBACK_COMMENTS, genres)
    previous_comments.append(comment)
    if len(previous_comments) > 10:
        previous_comments.pop(0)
    return comment

async def send_admin_alert(context: ContextTypes.DEFAULT_TYPE, message: str, reply_markup=None):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": ADMIN_ID, "text": message}
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup.to_dict())
            async with session.post(url, json=payload) as response:
                result = await response.json()
                if not result.get('ok'):
                    logger.error(f"خطا در ارسال هشدار به ادمین: {result}")
    except Exception as e:
        logger.error(f"خطا در ارسال هشدار به ادمین: {str(e)}")

async def fetch_movies_to_cache():
    global cached_movies, last_fetch_time
    logger.info("شروع آپدیت کش فیلم‌ها...")
    new_movies = []
    for attempt in range(5):
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
                page = 1
                while len(new_movies) < 100 and page <= 20:
                    # 1. TMDB
                    logger.info(f"تلاش با TMDB برای کش، صفحه {page}")
                    tmdb_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page={page}"
                    tmdb_data = await make_api_request(tmdb_url)
                    if tmdb_data and tmdb_data.get('results'):
                        for m in tmdb_data['results']:
                            if (m.get('title') and m.get('id') and
                                m.get('original_language') != 'hi' and
                                'IN' not in m.get('origin_country', []) and
                                m.get('poster_path')):
                                imdb_score = await get_imdb_score_tmdb(m['title'])
                                if imdb_score and float(imdb_score.split('/')[0]) >= 6.0:
                                    new_movies.append({'title': m['title'], 'id': str(m['id'])})
                        page += 1

                    # 2. OMDb
                    logger.info(f"تلاش با OMDb برای کش، صفحه {page}")
                    omdb_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&s=movie&type=movie&page={page}"
                    omdb_data = await make_api_request(omdb_url)
                    if omdb_data and omdb_data.get('Search'):
                        for m in omdb_data['Search']:
                            imdb_score = await get_imdb_score_omdb(m['Title'])
                            if imdb_score and float(imdb_score.split('/')[0]) >= 6.0:
                                new_movies.append({'title': m['Title'], 'id': m['imdbID']})
                        page += 1
                
                if new_movies:
                    cached_movies = new_movies[:100]
                    last_fetch_time = datetime.now()
                    await save_cache_to_file()
                    logger.info(f"لیست فیلم‌ها آپدیت شد. تعداد: {len(cached_movies)}")
                    return True
                logger.error("داده‌ای از هیچ API دریافت نشد")
        except Exception as e:
            logger.error(f"خطا در آپدیت کش (تلاش {attempt + 1}): {str(e)}")
            await asyncio.sleep(2 ** attempt)
    
    logger.error("تلاش‌ها برای آپدیت کش ناموفق بود، لود از فایل")
    if await load_cache_from_file():
        return True
    cached_movies = [{'title': m['title'], 'id': m['title']} for m in FALLBACK_MOVIES]
    await save_cache_to_file()
    last_fetch_time = datetime.now()
    await send_admin_alert(None, "❌ خطا: کش فیلم‌ها آپدیت نشد، استفاده از فال‌بک")
    return False

async def auto_fetch_movies(context: ContextTypes.DEFAULT_TYPE):
    logger.info("شروع آپدیت خودکار کش...")
    if await fetch_movies_to_cache():
        logger.info("آپدیت خودکار کش موفق بود")
    else:
        logger.error("خطا در آپدیت خودکار کش")
        await send_admin_alert(context, "❌ خطا در آپدیت خودکار کش")

async def get_random_movie(max_retries=5):
    logger.info("انتخاب فیلم تصادفی...")
    for attempt in range(max_retries):
        try:
            if not cached_movies or (datetime.now() - last_fetch_time).seconds > FETCH_INTERVAL:
                logger.info("کش خالی یا قدیمی، آپدیت کش...")
                await fetch_movies_to_cache()
            
            if not cached_movies:
                logger.error("هیچ فیلمی در کش موجود نیست، استفاده از فال‌بک")
                return random.choice(FALLBACK_MOVIES)
            
            available_movies = [m for m in cached_movies if m['id'] not in posted_movies]
            if not available_movies:
                logger.warning("هیچ فیلم جدیدی در کش نیست، ریست لیست پست‌شده‌ها")
                posted_movies.clear()
                await save_posted_movies_to_file()
                available_movies = cached_movies
            
            movie = random.choice(available_movies)
            logger.info(f"فیلم انتخاب شد: {movie['title']} (تلاش {attempt + 1})")
            movie_info = await get_movie_info(movie['title'])
            if not movie_info or movie_info['imdb'] == '0.0/10':
                logger.warning(f"اطلاعات فیلم {movie['title']} نامعتبر، تلاش مجدد...")
                continue
            
            # چک اضافی برای انیمیشن
            if 'انیمیشن' in movie_info['genres'] and float(movie_info['imdb'].split('/')[0]) < 8.0:
                logger.warning(f"فیلم {movie['title']} انیمیشن است اما امتیاز {movie_info['imdb']} دارد، رد شد")
                continue
            
            posted_movies.append(movie['id'])
            await save_posted_movies_to_file()
            logger.info(f"فیلم‌های ارسال‌شده: {posted_movies}")
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
            
            if movie_info['poster']:
                if not await check_poster(movie_info['poster']):
                    movie_info['poster'] = None
            
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
                return random.choice(FALLBACK_MOVIES)
    logger.error("تلاش‌ها تمام شد، استفاده از فال‌بک")
    return random.choice(FALLBACK_MOVIES)

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
            InlineKeyboardButton("ریست Webhook", callback_data='reset_webhook')
        ],
        [
            InlineKeyboardButton(toggle_text, callback_data='toggle_bot')
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
    msg = await query.message.edit_text("در حال آماده‌سازی پست (انتخاب فیلم)...")
    try:
        if not bot_enabled:
            logger.error("ارسال پست کنسل شد: ربات غیرفعال است")
            await msg.edit_text("❌ ارسال پست کنسل شد: ربات غیرفعال است", reply_markup=get_main_menu())
            return
        
        async with asyncio.timeout(120):  # تایم‌اوت 2 دقیقه
            movie = await get_random_movie()
            if not movie:
                logger.error("هیچ فیلمی انتخاب نشد")
                await msg.edit_text("❌ خطا در یافتن فیلم", reply_markup=get_main_menu())
                return
            
            await msg.edit_text(f"در حال آماده‌سازی پست برای {movie['title']} (تولید تحلیل)...")
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
    except asyncio.TimeoutError:
        logger.error("ارسال پست فوری به دلیل تایم‌اوت کنسل شد")
        await msg.edit_text("❌ ارسال پست به دلیل طولانی شدن (بیش از 2 دقیقه) کنسل شد", reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"خطا در post_now: {e}")
        await msg.edit_text(f"❌ خطا در ارسال پست: {str(e)}", reply_markup=get_main_menu())

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
                "temperature": 0.7
            }
            response = await post_api_request(url, data, headers, retries=3)
            text = response['choices'][0]['message']['content'].strip() if response and response.get('choices') else ""
            groq_status = "✅ Groq اوکی" if text and is_farsi(text) else f"❌ Groq خطا: پاسخ نامعتبر - متن دریافتی: {text}"
            results.append(groq_status)
        except Exception as e:
            logger.error(f"خطا در تست Groq: {str(e)}")
            api_availability['groq'] = False
            results.append(f"❌ Groq خطا: {str(e)}")

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
                temperature=0.7
            )
            text = response.choices[0].message.content.strip()
            openai_status = "✅ Open AI اوکی" if text and is_farsi(text) else "❌ Open AI خطا: پاسخ نامعتبر"
            results.append(openai_status)
        except Exception as e:
            logger.error(f"خطا در تست Open AI: {str(e)}")
            api_availability['openai'] = False
            results.append(f"❌ Open AI خطا: {str(e)}")

    return "\n".join(results)

async def test_all_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه test_all")
    await query.answer()
    msg = await query.message.edit_text("در حال اجرای تست‌ها...")
    try:
        results = await run_tests(update, context)
        await msg.edit_text(f"📋 نتایج تست:\n{results}", reply_markup=get_tests_menu())
    except Exception as e:
        logger.error(f"خطا در test_all: {str(e)}")
        await msg.edit_text(f"❌ خطا در اجرای تست‌ها: {str(e)}", reply_markup=get_tests_menu())

async def test_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه test_channel")
    await query.answer()
    msg = await query.message.edit_text("در حال تست دسترسی به کانال...")
    try:
        if not CHANNEL_ID:
            raise Exception("CHANNEL_ID تنظیم نشده است.")
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember?chat_id={CHANNEL_ID}&user_id={context.bot.id}"
            async with session.get(url) as response:
                data = await response.json()
                if not data.get('ok'):
                    raise Exception(f"خطا در API تلگرام: {data.get('description')}")
                if data['result']['status'] not in ['administrator', 'creator']:
                    raise Exception("بات ادمین کانال نیست یا CHANNEL_ID اشتباه است.")
        await msg.edit_text("✅ دسترسی به کانال اوکی", reply_markup=get_tests_menu())
    except Exception as e:
        logger.error(f"خطا در تست دسترسی به کانال: {str(e)}")
        await msg.edit_text(f"❌ خطا در تست دسترسی به کانال: {str(e)}", reply_markup=get_tests_menu())

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
        await send_admin_alert(None, f"❌ خطا در ساخت بات: {str(e)}")
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
    app.add_handler(CallbackQueryHandler(show_movies_handler, pattern='^show_movies$'))
    app.add_handler(CallbackQueryHandler(toggle_bot_handler, pattern='^toggle_bot$'))
    app.add_handler(CallbackQueryHandler(reset_webhook_handler, pattern='^reset_webhook$'))
    
    job_queue = app.job_queue
    if job_queue:
        logger.info("JobQueue فعال شد")
        job_queue.run_repeating(auto_post, interval=POST_INTERVAL, first=10)
        job_queue.run_repeating(auto_fetch_movies, interval=FETCH_INTERVAL, first=60)
    else:
        logger.error("JobQueue فعال نشد، ربات متوقف می‌شود")
        await send_admin_alert(None, "❌ خطا: JobQueue فعال نشد. لطفاً ربات را بررسی کنید.")
        global bot_enabled
        bot_enabled = False
        raise Exception("JobQueue غیرفعال است")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("بات تلگرام با موفقیت راه‌اندازی شد")
    return app

async def main():
    logger.info("شروع برنامه...")
    await init_openai_client()  # مقداردهی Open AI client
    await load_cache_from_file()
    await load_posted_movies_from_file()
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
        await send_admin_alert(None, f"❌ خطا در ریست Webhook اولیه: {str(e)}")
    
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
        if client:
            await client.close()

if __name__ == '__main__':
    asyncio.run(main())
