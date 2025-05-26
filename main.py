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
import aiohttp.client_exceptions
import re
import certifi

# تنظیمات اولیه
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO # می‌توانید برای دیباگ به logging.DEBUG تغییر دهید
)
logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
ADMIN_ID = os.getenv('ADMIN_ID')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
PORT = int(os.getenv('PORT', 8080))
POST_INTERVAL = int(os.getenv('POST_INTERVAL', 14400)) # 4 hours in seconds
FETCH_INTERVAL = int(os.getenv('FETCH_INTERVAL', 86400)) # 24 hours in seconds

# تنظیم Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# وضعیت دسترسی APIها
api_availability = {
    'gemini': True,
}

# کش و متغیرهای سراسری
cached_movies = []
posted_movies = []
last_fetch_time = datetime.now() - timedelta(days=1)
previous_plots = []
previous_comments = []
bot_enabled = True
CACHE_FILE = "movie_cache.json"
POSTED_MOVIES_FILE = "posted_movies.json"

# دیکشنری ترجمه ژانرها
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

# فال‌بک‌ها برای هر ژانر
FALLBACK_COMMENTS = {
    'اکشن': [
        'داستان پر از تحرکه و صحنه‌های اکشن نفس‌گیرن، ولی گاهی منطقش گم می‌شه. شخصیت‌پردازی ساده‌ست، اما کارگردانی پرهیجانه. جلوه‌های بصری چشم‌گیرن و موسیقی حسابی جون می‌ده. تجربه‌ایه که آدرنالینت رو بالا می‌بره.',
        'فیلم با اکشن قوی شروع می‌شه، ولی داستانش گاهی گنگه. شخصیت‌ها معمولی‌ان، اما کارگردانی ریتم خوبی داره. موسیقی متن به هیجانش کمک می‌کنه. حس و حالش تو رو به فکر یه ماجراجویی پرسرعت می‌بره.',
        'داستان اکشن جذابه، ولی پایانش یه کم قابل پیش‌بینیه. شخصیت‌پردازی می‌تونست عمیق‌تر باشه، اما جلوه‌های بصری قوین. کارگردانی پرانرژیه. این فیلم یه تجربه پرهیجان و کنجکاوی‌برانگیزه.',
        'صحنه‌های اکشن فیلم خیلی قوین، ولی داستانش گاهی کند می‌شه. شخصیت‌ها ساده‌ان، اما موسیقی متن به فضا عمق می‌ده. کارگردانی با دقته. تجربه‌ایه که ذهنت رو مشغول می‌کنه.',
        'داستان پر از تعلیقه، ولی گاهی زیاده‌روی می‌کنه. شخصیت‌پردازی متوسطه، اما جلوه‌های بصری و موسیقی قوین. کارگردانی ریتم خوبی داره. این فیلم یه حس ماجراجویانه تو بیدار می‌کنه.'
    ],
    'درام': [
        'داستان فیلم عمیق و احساسیه، ولی گاهی ریتمش کند می‌شه. شخصیت‌پردازی خوبه، اما بعضی نقش‌ها کم‌عمقن. کارگردانی با دقت انجام شده و موسیقی به صحنه‌ها حس می‌ده. تجربه‌ایه که تو رو به فکر وا می‌داره.',
        'فیلم داستانی احساسی داره، ولی پایانش یه کم گنگه. شخصیت‌پردازی قویه، اما ریتم گاهی یکنواخت می‌شه. موسیقی متن فضا رو عمیق‌تر می‌کنه. حس و حالش یه تأمل عمیق تو دلت می‌ذاره.',
        'داستان دراماتیک و جذابه، ولی گاهی زیاده‌روی می‌کنه. شخصیت‌ها باورپذیرن، اما کارگردانی می‌تونست منسجم‌تر باشه. موسیقی متن قویه. این فیلم یه تجربه احساسی و تأمل‌برانگیزه.',
        'داستان فیلم پر از احساسه، ولی تمرکز داستان گاهی گم می‌شه. شخصیت‌پردازی خوبه، اما موسیقی متن می‌تونست قوی‌تر باشه. کارگردانی ساده و صمیمیه. تجربه‌ایه که تو رو به فکر فرو می‌بره.',
        'فیلم داستانی عمیق داره، ولی ریتمش گاهی کند می‌شه. شخصیت‌ها قابل قبوله، اما پایانش معمولیه. کارگردانی و موسیقی حس خوبی می‌دن. این فیلم یه حس واقعی و کنجکاوی‌برانگیز داره.'
    ],
    'کمدی': [
        'داستان فیلم شاد و بامزه‌ست، ولی بعضی شوخی‌ها تکراری‌ان. شخصیت‌پردازی ساده‌ست، اما کارگردانی ریتم خوبی داره. موسیقی متن به فضا انرژی می‌ده. این فیلم یه حس سبُک و سرگرم‌کننده بهت می‌ده.',
        'فیلم پر از لحظه‌های خنده‌داره، ولی داستانش خیلی عمیق نیست. شخصیت‌ها دوست‌داشتنی‌ان، اما پایانش معمولیه. کارگردانی شاده و موسیقی مناسبه. حس و حالش تو رو به یه لبخند دعوت می‌کنه.',
        'داستان کمدی جذابه، ولی گاهی ریتمش افت می‌کنه. شخصیت‌پردازی متوسطه، اما کارگردانی پرنشاطه. موسیقی متن به فضا جون می‌ده. این فیلم یه تجربه بامزه و فکربرانگیزه.',
        'فیلم سبُک و خنده‌دار شروع می‌شه، ولی بعضی جاها زیاده‌روی می‌کنه. شخصیت‌ها معمولی‌ان، اما موسیقی متن شاده. کارگردانی حس خوبی داره. تجربه‌ایه که حالتو خوب می‌کنه.',
        'داستان کمدی فیلم بامزه‌ست، ولی پایانش یه کم ساده‌ست. شخصیت‌پردازی خوبه، اما کارگردانی می‌تونست خلاق‌تر باشه. موسیقی متن انرژی می‌ده. این فیلم یه حس شاد و کنجکاوی‌برانگیز داره.'
    ],
    'علمی_تخیلی': [
        'داستان فیلم پر از ایده‌های جدیده، ولی گاهی گنگ می‌شه. شخصیت‌پردازی ساده‌ست، اما جلوه‌های بصری خیره‌کننده‌ان. کارگردانی خلاقه و موسیقی فضا رو عمیق می‌کنه. این فیلم ذهنت رو به یه دنیای دیگه می‌بره.',
        'فیلم ایده‌های تخیلی جذابی داره، ولی ریتمش گاهی کند می‌شه. شخصیت‌ها متوسطه، اما کارگردانی قویه. جلوه‌های بصری و موسیقی خیلی خوبن. حس و حالش تو رو به فکر فرو می‌بره.',
        'داستان علمی تخیلی پر از خلاقیته، ولی پایانش یه کم گنگه. شخصیت‌پردازی می‌تونست بهتر باشه، اما جلوه‌های بصری قوین. کارگردانی جذابه. این فیلم یه تجربه کنجکاوی‌برانگیزه.',
        'فیلم با دنیای تخیلی جذابی شروع می‌شه، ولی منطق داستان گاهی لنگ می‌زنه. شخصیت‌ها معمولی‌ان، اما موسیقی و کارگردانی قوین. جلوه‌های بصری چشم‌گیرن. تجربه‌ایه که ذهنت رو مشغول می‌کنه.',
        'داستان تخیلی فیلم جذابه، ولی ریتمش گاهی یکنواخت می‌شه. شخصیت‌پردازی متوسطه، اما جلوه‌های بصری و موسیقی خوبن. کارگردانی خلاقه. این فیلم یه حس عجیب و تأمل‌برانگیز داره.'
    ],
    'هیجان_انگیز': [
        'داستان پر از تعلیقه و حسابی نفس‌گیره، ولی گاهی قابل پیش‌بینیه. شخصیت‌پردازی خوبه، اما پایانش ساده‌ست. کارگردانی قویه و موسیقی حس تعلیق رو بالا می‌بره. این فیلم ذهنت رو درگیر می‌کنه.',
        'فیلم پر از پیچش‌های داستانیه، ولی ریتمش گاهی افت می‌کنه. شخصیت‌ها متوسطه، اما کارگردانی هیجان‌انگیزه. موسیقی متن به فضا جون می‌ده. حس و حالش تو رو کنجاو نگه می‌داره.',
        'داستان هیجان‌انگیز جذابه، ولی گاهی زیاده‌روی می‌کنه. شخصیت‌پردازی ساده‌ست، اما کارگردانی قویه. موسیقی متن حس تعلیق رو خوب منتقل می‌کنه. این فیلم یه تجربه پرهیجان و تأمل‌برانگیزه.',
        'فیلم با تعلیق قوی شروع می‌شه، ولی پایانش یه کم گنگه. شخصیت‌ها قابل قبوله، اما موسیقی می‌تونست بهتر باشه. کارگردانی جذابه. تجربه‌ایه که تو رو به فکر وا می‌داره.',
        'داستان پر از هیجانه، ولی منطقش گاهی لنگ می‌زنه. شخصیت‌پردازی متوسطه، اما کارگردانی و موسیقی قوین. جلوه‌های بصری خوبن. این فیلم یه حس کنجکاوی و هیجان بهت می‌ده.'
    ],
    'سایر': [
        'داستان فیلم متفاوته و حس جالبی داره، ولی ریتمش گاهی کند می‌شه. شخصیت‌پردازی خوبه، اما پایانش معمولیه. کارگردانی ساده و موسیقی قویه. این فیلم یه تجربه کنجکاوی‌برانگیز و تأمل‌برانگیزه.',
        'فیلم داستانی عجیب داره، ولی گاهی تمرکز داستان گم می‌شه. شخصیت‌ها متوسطه، اما جلوه‌های بصری خوبن. کارگردانی و موسیقی حس خوبی می‌دن. حس و حالش تو رو به فکر فرو می‌بره.',
        'داستان فیلم جذابه، ولی ریتمش گاهی یکنواخت می‌شه. شخصیت‌پردازی ساده‌ست، اما کارگردانی قویه. موسیقی متن به فضا جون می‌ده. این فیلم یه حس خاص و تأمل‌برانگیز داره.',
        'فیلم با ایده‌های جدید شروع می‌شه، ولی پایانش یه کم ساده‌ست. شخصیت‌ها قابل قبوله، اما موسیقی می‌تونست قوی‌تر باشه. کارگردانی جذابه. تجربه‌ایه که ذهنت رو مشغول می‌کنه.',
        'داستان فیلم خاصه، ولی گاهی زیاده‌روی می‌کنه. شخصیت‌پردازی متوسطه، اما کارگردانی و جلوه‌های بصری خوبن. موسیقی متن قویه. این فیلم یه حس کنجکاوی و فکربرانگیز بهت می‌ده.'
    ]
}

# شمارشگر خطاهای API (فقط برای OMDb و TMDB)
api_errors = {
    'tmdb': 0,
    'omdb': 0
}

# توابع کمکی
def clean_text(text):
    if not text or text == 'N/A':
        return None
    return text[:500]

def shorten_plot(text, max_sentences=3):
    sentences = [s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟']
    result = '. '.join(sentences[:max_sentences]).rstrip('.')
    return result if result else ''

def clean_text_for_validation(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[\n\t]', ' ', text)
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
    if not text:
        return False
    text = clean_text_for_validation(text)
    if not is_farsi(text):
        logger.warning(f"تحلیل رد شد: متن غیرفارسی - {text}")
        return False
    words = text.split()
    if len(words) < 50 or len(words) > 120:
        logger.warning(f"تحلیل رد شد: تعداد کلمات {len(words)} (باید بین 50 تا 120 باشد) - {text}")
        return False
    sentences = text.split('. ')
    last_sentence = sentences[-1].strip() if sentences else ""
    if last_sentence and last_sentence[-1] not in '.!؟':
        logger.warning(f"تحلیل رد شد: جمله آخر ناقص است - {text}")
        return False
    if text in previous_comments:
        logger.warning(f"تحلیل رد شد: متن تکراری - {text}")
        return False
    if '[نام بازیگر]' in text or re.search(r'\[\w+\]', text):
        logger.warning(f"تحلیل رد شد: شامل عبارات مبهم مثل [نام بازیگر] - {text}")
        return False
    return True

def shorten_comment(text):
    """کوتاه کردن تحلیل به 50-120 کلمه با حفظ جملات کامل"""
    text = clean_text_for_validation(text)
    sentences = [s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟']
    result = []
    word_count = 0
    for sentence in sentences:
        sentence_words = sentence.split()
        if word_count + len(sentence_words) <= 120:
            result.append(sentence)
            word_count += len(sentence_words)
        else:
            break
    shortened_text = '. '.join(result).rstrip('.')
    if 50 <= len(shortened_text.split()) <= 120 and is_valid_comment(shortened_text):
        return shortened_text
    return None

# تابع برای گرفتن IMDb ID از TMDB
async def get_imdb_id_from_tmdb(tmdb_movie_id):
    url = f"https://api.themoviedb.org/3/movie/{tmdb_movie_id}/external_ids?api_key={TMDB_API_KEY}"
    data = await make_api_request(url)
    if data and data.get("imdb_id"):
        return data["imdb_id"]
    logger.warning(f"هیچ IMDb ID برای TMDB ID {tmdb_movie_id} یافت نشد")
    return None

# تابع برای گرفتن نمرات از RapidAPI (Movies Ratings) با استفاده از IMDb ID
async def get_ratings_from_rapidapi(imdb_id):
    logger.info(f"درخواست به RapidAPI (Movies Ratings) با IMDb ID: {imdb_id}")
    if not imdb_id or not isinstance(imdb_id, str) or not imdb_id.startswith("tt"):
        logger.error(f"IMDb ID نامعتبر برای RapidAPI: {imdb_id}")
        return None
    if not RAPIDAPI_KEY:
        logger.error("RAPIDAPI_KEY تنظیم نشده است.")
        return None
    
    url = "https://movies-ratings2.p.rapidapi.com/ratings"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "movies-ratings2.p.rapidapi.com"
    }
    querystring = {"imdb_id": imdb_id}
    
    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=15)) as session:
            async with session.get(url, headers=headers, params=querystring) as response:
                if response.status == 422:
                    logger.error(f"خطای 422: درخواست RapidAPI نامعتبر. پاسخ: {await response.text()}")
                    return None
                if response.status == 401:
                    logger.error("خطای 401: کلید RapidAPI نامعتبر")
                    return None
                if response.status == 429: # Rate Limit
                    logger.warning(f"خطای 429: RapidAPI Rate Limit. فال‌بک به TMDB/OMDb.")
                    return None
                if response.status != 200:
                    logger.error(f"خطای RapidAPI: کد {response.status}, پاسخ: {await response.text()}")
                    return None
                data = await response.json()
                logger.info(f"داده‌های RapidAPI دریافت شد: {data}")
                return {
                    "imdb_rating": data.get("imdb_rating"),
                    "imdb_votes": data.get("imdb_votes"),
                    "rotten_tomatoes": data.get("rotten_tomatoes_rating"),
                    "metacritic": data.get("metacritic_rating"),
                }
    except Exception as e:
        logger.error(f"خطا در درخواست RapidAPI: {str(e)}")
        return None

async def translate_plot(plot, title):
    logger.info(f"تلاش برای ترجمه خلاصه داستان برای {title}")
    
    # 1. Gemini
    if api_availability['gemini'] and GOOGLE_API_KEY:
        logger.info("تلاش با Gemini برای ترجمه")
        try:
            async with asyncio.timeout(15):
                # تغییر مدل به gemini-1.5-flash
                model = genai.GenerativeModel('gemini-1.5-flash') 
                prompt = f"خلاصه داستان فیلم را از انگلیسی به فارسی ترجمه کن. ترجمه باید دقیق و مناسب برای خلاصه فیلم باشد. فقط از فارسی استفاده کن: {plot}"
                response = await model.generate_content_async(
                    prompt,
                    generation_config=genai.types.GenerationConfig(max_output_tokens=300) # افزایش max_tokens برای ترجمه
                )
                translated_plot = clean_text_for_validation(response.text.strip())
                if is_valid_plot(translated_plot) and is_farsi(translated_plot):
                    logger.info(f"ترجمه Gemini موفق برای {title}: {translated_plot[:100]}...")
                    return translated_plot
                logger.warning(f"ترجمه Gemini نامعتبر برای {title}: {translated_plot}")
        except google_exceptions.ResourceExhausted:
            logger.error("خطا: توکن Gemini تمام شده است")
            api_availability['gemini'] = False
            await send_admin_alert(None, "❌ توکن Gemini تمام شده است.")
        except Exception as e:
            logger.error(f"خطا در ترجمه Gemini برای {title}: {str(e)}")
            api_availability['gemini'] = False
            await send_admin_alert(None, f"❌ خطا در ترجمه Gemini: {str(e)}.")

    logger.error(f"هیچ ترجمه‌ای برای {title} تولید نشد")
    return None

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
                        logger.error(f"خطای 401: کلید API نامعتبر برای {url}")
                        return None
                    if response.status != 200:
                        logger.error(f"خطای {response.status}: {await response.text()} برای {url}")
                        return None
                    data = await response.json()
                    return data
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.error(f"خطای اتصال (تلاش {attempt + 1}) برای {url}: {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except aiohttp.ClientResponseError as e:
            logger.error(f"خطای پاسخ (تلاش {attempt + 1}) برای {url}: {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"خطای غیرمنتظره در درخواست API (تلاش {attempt + 1}) برای {url}: {str(e)}")
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
                        logger.error(f"خطای 401: کلید API نامعتبر برای {url}")
                        return None
                    if response.status != 200:
                        logger.error(f"خطای {response.status}: {await response.text()} برای {url}")
                        return None
                    return await response.json()
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.error(f"خطای اتصال (تلاش {attempt + 1}) برای {url}: {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except aiohttp.ClientResponseError as e:
            logger.error(f"خطای پاسخ (تلاش {attempt + 1}) برای {url}: {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"خطای غیرمنتظره در درخواست API (تلاش {attempt + 1}) برای {url}: {str(e)}")
            if attempt == retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
    return None

async def check_poster(url):
    try:
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=5)) as session:
            async with session.head(url) as response:
                if response.status != 200:
                    return False
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > 5 * 1024 * 1024:
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

async def get_movie_info(title, tmdb_movie_id=None):
    """
    این تابع اطلاعات اولیه فیلم (عنوان، سال، پوستر، ژانر، خلاصه داستان، IMDb ID) را از TMDB دریافت می‌کند.
    نمرات دقیق RapidAPI در این مرحله دریافت نمی‌شوند، بلکه در fetch_movies_to_cache یا get_random_movie مدیریت می‌شوند.
    """
    logger.info(f"دریافت اطلاعات اولیه برای فیلم: {title}")
    
    movie_info = {}
    
    # 1. TMDB - دریافت اطلاعات اولیه و IMDb ID
    encoded_title = urllib.parse.quote(title)
    
    movie = None
    if tmdb_movie_id: # اگر TMDB ID از قبل داشتیم
        details_url_en = f"https://api.themoviedb.org/3/movie/{tmdb_movie_id}?api_key={TMDB_API_KEY}&language=en-US"
        movie = await make_api_request(details_url_en)
        if not movie:
            logger.warning(f"جزئیات TMDB برای TMDB ID {tmdb_movie_id} دریافت نشد")
            return None
    else: # اگر TMDB ID نداشتیم، جستجو می‌کنیم
        search_url_en = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=en-US"
        tmdb_data_en = await make_api_request(search_url_en)
        if not tmdb_data_en or not tmdb_data_en.get('results'):
            logger.warning(f"TMDB هیچ نتیجه‌ای برای {title} نداد")
            api_errors['tmdb'] += 1
            return None
        movie = tmdb_data_en['results'][0]
        tmdb_movie_id = movie.get('id')

    movie_info['title'] = movie.get('title', title)
    movie_info['year'] = movie.get('release_date', 'N/A')[:4]
    movie_info['poster'] = f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else None

    # گرفتن IMDb ID از TMDB
    movie_info['imdb_id'] = await get_imdb_id_from_tmdb(tmdb_movie_id)
    movie_info['tmdb_id'] = tmdb_movie_id # برای استفاده در کش

    genres = [GENRE_TRANSLATIONS.get(g['name'], 'سایر') for g in movie.get('genres', [])]
    if not genres and tmdb_movie_id: # اگر ژانرها در جستجو نبود، از جزئیات بیشتر بگیر
        details_url = f"https://api.themoviedb.org/3/movie/{tmdb_movie_id}?api_key={TMDB_API_KEY}&language=en-US"
        details_data = await make_api_request(details_url)
        if details_data:
            genres = [GENRE_TRANSLATIONS.get(g['name'], 'سایر') for g in details_data.get('genres', [])]

    movie_info['genres'] = genres[:3]
    
    if 'مستند' in movie_info['genres']:
        logger.warning(f"فیلم {movie_info['title']} مستند است، رد شد")
        return None

    # تلاش برای خلاصه داستان فارسی
    search_url_fa = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=fa-IR"
    tmdb_data_fa = await make_api_request(search_url_fa)
    tmdb_plot_fa = tmdb_data_fa['results'][0].get('overview', '') if tmdb_data_fa and tmdb_data_fa.get('results') else ''
    
    if tmdb_plot_fa and is_farsi(tmdb_plot_fa) and is_valid_plot(tmdb_plot_fa):
        logger.info(f"خلاصه داستان فارسی معتبر از TMDB برای {movie_info['title']}")
        movie_info['plot'] = shorten_plot(tmdb_plot_fa)
    else:
        logger.warning(f"خلاصه داستان TMDB فارسی نامعتبر برای {movie_info['title']}. تلاش برای ترجمه انگلیسی.")
        tmdb_plot_en = movie.get('overview', '')
        if tmdb_plot_en:
            translated_plot = await translate_plot(tmdb_plot_en, movie_info['title'])
            if translated_plot:
                movie_info['plot'] = shorten_plot(translated_plot)
            else:
                logger.error(f"ترجمه خلاصه داستان برای {movie_info['title']} ناموفق بود")
                return None
        else:
            logger.error(f"هیچ خلاصه داستان انگلیسی برای {movie_info['title']} یافت نشد")
            return None

    # در این مرحله، نمرات دقیق از RapidAPI گرفته نمی‌شوند.
    # فقط ساختار imdb را با مقادیر اولیه TMDB آماده می‌کنیم.
    movie_info['imdb'] = {
        "imdb": f"{float(movie.get('vote_average', 0)):.1f}/10" if movie.get('vote_average') else None,
        "imdb_votes": movie.get('vote_count'),
        "rotten_tomatoes": None, # در این مرحله خالی هستند
        "metacritic": None # در این مرحله خالی هستند
    }
    
    # بررسی حداقل امتیاز با استفاده از امتیاز TMDB (که در fetch_movies_to_cache هم استفاده می‌شود)
    min_score = 8.0 if 'انیمیشن' in movie_info['genres'] else 6.0
    tmdb_current_score = float(movie.get('vote_average', 0))

    if tmdb_current_score < min_score:
        logger.warning(f"فیلم {movie_info['title']} امتیاز {tmdb_current_score} (TMDB) دارد، رد شد (حداقل {min_score} لازم است).")
        return None

    previous_plots.append(movie_info['plot'])
    if len(previous_plots) > 10:
        previous_plots.pop(0)
    
    return movie_info

async def generate_comment(genres, imdb_score_val):
    logger.info(f"تولید تحلیل برای امتیاز: {imdb_score_val}")
    logger.info(f"وضعیت APIها: Gemini={api_availability['gemini']}")

    # انتخاب ژانر برای فال‌بک
    selected_genre = None
    for genre in genres:
        if genre in FALLBACK_COMMENTS:
            selected_genre = genre
            break
    if not selected_genre:
        selected_genre = 'سایر'
    logger.info(f"ژانر انتخاب‌شده برای تحلیل/فال‌بک: {selected_genre}")

    # پرامپت‌های شرطی بر اساس امتیاز فیلم
    if imdb_score_val >= 8.5:
        prompt = """یک تحلیل بسیار تحسین‌آمیز و پرانرژی درباره فیلم بنویس. بر نقاط قوت بی‌نظیر فیلم (مانند کارگردانی خلاقانه، بازی‌های درخشان، داستان‌گویی عمیق، جلوه‌های بصری خیره‌کننده، موسیقی مسحورکننده) تمرکز کن. هیچ نقطه ضعفی ذکر نکن. متن بین 60 تا 100 کلمه باشد. جمله آخر باید یک توصیه قاطع برای تماشا باشد که بر تجربه فراموش‌نشدنی تأکید کند. از زبان ساده و روان استفاده کن. مهم است که هر تحلیل، ساختار جملات، انتخاب واژگان و زاویه دید متفاوتی نسبت به تحلیل‌های قبلی داشته باشد تا از تکراری شدن جلوگیری شود. از ذکر نام فیلم یا بازیگر و تشبیهات بسیار اغراق‌آمیز خودداری کن."""
    elif 7.0 <= imdb_score_val < 8.5:
        prompt = """یک تحلیل متعادل و واقع‌بینانه درباره فیلم بنویس. به نقاط قوت (مانند کارگردانی مناسب، بازی‌های قابل قبول، داستانی جذاب) و همچنین یک یا دو نکته که می‌توانست بهتر باشد (مثلاً ریتم کند، پایان قابل پیش‌بینی، شخصیت‌پردازی سطحی) اشاره کن. متن بین 50 تا 80 کلمه باشد. جمله آخر باید یک جمع‌بندی منطقی و بدون اغراق باشد که تماشای آن را به طور کلی به عنوان یک تجربه سرگرم‌کننده توصیه کند. از زبان ساده و روان استفاده کن. مهم است که هر تحلیل، ساختار جملات، انتخاب واژگان و زاویه دید متفاوتی نسبت به تحلیل‌های قبلی داشته باشد تا از تکراری شدن جلوگیری شود. از ذکر نام فیلم یا بازیگر خودداری کن."""
    else: # امتیاز کمتر از 7.0 (مثلاً 6.0 تا 6.9)
        prompt = """یک تحلیل صریح و منصفانه درباره فیلم بنویس. بر نقاط ضعف اصلی فیلم (مانند داستان کلیشه‌ای، کارگردانی ضعیف، بازی‌های غیرطبیعی، نقص‌های فنی) تمرکز کن، اما به نکات مثبت کوچک نیز اشاره کن (مثلاً یک ایده اولیه خوب یا یک صحنه خاص). متن بین 50 تا 80 کلمه باشد. جمله آخر باید یک جمع‌بندی واقع‌بینانه باشد که تماشای فیلم را برای اوقات فراغت یا علاقه‌مندان به سبک‌های خاص (بدون ذکر مستقیم ژانر) مناسب بداند. مهم است که هر تحلیل، ساختار جملات، انتخاب واژگان و زاویه دید متفاوتی نسبت به تحلیل‌های قبلی داشته باشد تا از تکراری شدن جلوگیری شود. از ذکر نام فیلم یا بازیگر خودداری کن."""
    # 1. Gemini
    if api_availability['gemini'] and GOOGLE_API_KEY:
        logger.info("تلاش با Gemini")
        try:
            async with asyncio.timeout(25): # افزایش تایم‌اوت بیشتر
                # مدل به gemini-1.5-flash تغییر یافت. اگر 2.5-flash در دسترس شماست، می‌توانید در اینجا تغییر دهید.
                model = genai.GenerativeModel('gemini-1.5-flash') 
                response = await model.generate_content_async(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=250, # افزایش max_tokens
                        temperature=0.8 # تنظیم دما
                    ) 
                )
                text = clean_text_for_validation(response.text.strip())
                if is_valid_comment(text):
                    previous_comments.append(text)
                    if len(previous_comments) > 30: # افزایش اندازه previous_comments
                        previous_comments.pop(0)
                    logger.info("تحلیل Gemini با موفقیت دریافت شد")
                    return text.rstrip('.')
                logger.warning(f"تحلیل Gemini نامعتبر: {text}")
                shortened_text = shorten_comment(text)
                if shortened_text:
                    previous_comments.append(shortened_text)
                    if len(previous_comments) > 30:
                        previous_comments.pop(0)
                    logger.info("تحلیل Gemini کوتاه‌شده با موفقیت دریافت شد")
                    return shortened_text.rstrip('.')
        except google_exceptions.ResourceExhausted:
            logger.error("خطا: توکن Gemini تمام شده است")
            api_availability['gemini'] = False
            await send_admin_alert(None, "❌ توکن Gemini تمام شده است.")
        except Exception as e:
            logger.error(f"خطا در Gemini API: {str(e)}")
            api_availability['gemini'] = False
            await send_admin_alert(None, f"❌ خطا در Gemini: {str(e)}.")
    
    # 2. فال‌بک موقت (Groq و OpenAI حذف شدند)
    logger.warning(f"هیچ تحلیلگری AI در دسترس نیست، استفاده از فال‌بک موقت برای ژانر {selected_genre}")
    fallback_comment = random.choice(FALLBACK_COMMENTS[selected_genre])
    if is_valid_comment(fallback_comment):
        previous_comments.append(fallback_comment)
        if len(previous_comments) > 30:
            previous_comments.pop(0)
        logger.info(f"تحلیل فال‌بک با موفقیت استفاده شد: {fallback_comment}")
        await send_admin_alert(None, f"⚠️ هشدار: تحلیل با فال‌بک تولید شد (ژانر: {selected_genre}). لطفاً کلید API Gemini را بررسی کنید.")
        return fallback_comment.rstrip('.')
    
    logger.error("حتی فال‌بک هم ناموفق بود")
    await send_admin_alert(None, "❌ خطا: هیچ تحلیلی تولید نشد، لطفاً پرامپت‌ها و APIها را بررسی کنید.")
    return None

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
    new_movies_temp = []
    
    # محدودیت تعداد درخواست RapidAPI در مرحله کش
    rapidapi_calls_made_this_fetch = 0
    MAX_RAPIDAPI_CALLS_PER_FETCH = 8 # مثلا 8 درخواست در هر بار فچ (از 10 محدودیت روزانه)

    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=30)) as session:
                page = 1
                while len(new_movies_temp) < 100 and page <= 5: 
                    logger.info(f"تلاش با TMDB برای کش، صفحه {page}")
                    tmdb_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page={page}"
                    tmdb_data = await make_api_request(tmdb_url)
                    
                    if tmdb_data and tmdb_data.get('results'):
                        for m in tmdb_data['results']:
                            if not (m.get('title') and m.get('id') and m.get('poster_path')):
                                logger.warning(f"فیلم TMDB بدون اطلاعات کافی: {m}")
                                continue
                            if m.get('original_language') == 'hi' or 'IN' in m.get('origin_country', []):
                                logger.info(f"فیلم {m['title']} به دلیل زبان یا کشور رد شد")
                                continue
                            
                            imdb_id = await get_imdb_id_from_tmdb(m.get('id'))
                            if not imdb_id:
                                logger.warning(f"IMDb ID برای فیلم TMDB {m['title']} یافت نشد، رد شد.")
                                continue
                            
                            # بررسی ژانر مستند
                            details_url = f"https://api.themoviedb.org/3/movie/{m.get('id')}?api_key={TMDB_API_KEY}&language=en-US"
                            details_data = await make_api_request(details_url)
                            if not details_data:
                                logger.warning(f"جزئیات TMDB برای {m['title']} دریافت نشد")
                                continue
                            genres = [GENRE_TRANSLATIONS.get(g['name'], 'سایر') for g in details_data.get('genres', [])]
                            if 'مستند' in genres:
                                logger.info(f"فیلم {m['title']} مستند است، رد شد")
                                continue
                            
                            # اضافه کردن لینک تریلر
                            trailer = None
                            videos_url = f"https://api.themoviedb.org/3/movie/{m.get('id')}/videos?api_key={TMDB_API_KEY}&language=en"
                            videos_data = await make_api_request(videos_url)
                            if videos_data and videos_data.get('results'):
                                for video in videos_data['results']:
                                    if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                        trailer = f"https://www.youtube.com/watch?v={video['key']}"
                                        break

                            movie_cache_entry = {
                                'title': m['title'],
                                'id': imdb_id, # IMDb ID به عنوان ID اصلی
                                'tmdb_id': m['id'], # TMDB ID برای دسترسی مجدد به اطلاعات بیشتر TMDB
                                'year': m.get('release_date', 'N/A')[:4],
                                'poster': f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get('poster_path') else None,
                                'trailer': trailer, # <-- این خط اضافه شد
                                'genres': genres[:3],
                                'plot': None, # خلاصه داستان در get_movie_info کامل می‌شود
                                'imdb': { # اطلاعات امتیاز اولیه از TMDB
                                    "imdb": f"{float(m.get('vote_average', 0)):.1f}/10" if m.get('vote_average') else None,
                                    "imdb_votes": m.get('vote_count'),
                                    "rotten_tomatoes": None,
                                    "metacritic": None,
                                }
                            }

                            # تلاش برای دریافت نمرات دقیق RapidAPI در مرحله کش
                            if rapidapi_calls_made_this_fetch < MAX_RAPIDAPI_CALLS_PER_FETCH:
                                rapidapi_ratings = await get_ratings_from_rapidapi(imdb_id)
                                if rapidapi_ratings:
                                    movie_cache_entry['imdb'].update({
                                        "imdb": rapidapi_ratings.get("imdb_rating") or movie_cache_entry['imdb']['imdb'],
                                        "imdb_votes": rapidapi_ratings.get("imdb_votes") or movie_cache_entry['imdb']['imdb_votes'],
                                        "rotten_tomatoes": rapidapi_ratings.get("rotten_tomatoes"),
                                        "metacritic": rapidapi_ratings.get("metacritic"),
                                    })
                                    rapidapi_calls_made_this_fetch += 1
                                    logger.info(f"نمرات RapidAPI برای {m['title']} در کش ذخیره شد. تعداد درخواست: {rapidapi_calls_made_this_fetch}")
                                else:
                                    logger.warning(f"RapidAPI نمرات دقیق برای {m['title']} را نداد. استفاده از TMDB/OMDB.")
                            else:
                                logger.info(f"محدودیت درخواست RapidAPI در fetch_movies_to_cache به {MAX_RAPIDAPI_CALLS_PER_FETCH} رسید. ادامه بدون RapidAPI.")
                            
                            new_movies_temp.append(movie_cache_entry)
                            if len(new_movies_temp) >= 100:
                                break
                        page += 1
                    else:
                        logger.warning(f"هیچ نتیجه‌ای از TMDB برای صفحه {page} دریافت نشد.")
                        break

                # فیلتر کردن فیلم‌های تکراری در new_movies_temp بر اساس IMDb ID
                unique_movies = {}
                for movie in new_movies_temp:
                    if movie['id'] not in unique_movies:
                        unique_movies[movie['id']] = movie
                cached_movies = list(unique_movies.values())[:100]
                
                if cached_movies:
                    last_fetch_time = datetime.now()
                    await save_cache_to_file()
                    logger.info(f"لیست فیلم‌ها آپدیت شد. تعداد: {len(cached_movies)}")
                    return True
                logger.error("داده‌ای از هیچ API دریافت نشد")
        except Exception as e:
            logger.error(f"خطا در آپدیت کش (تلاش {attempt + 1}): {str(e)}", exc_info=True)
            await asyncio.sleep(2 ** attempt)
    
    logger.error("تلاش‌ها برای آپدیت کش ناموفق بود، لود از فایل")
    if await load_cache_from_file():
        return True
    cached_movies = []
    await save_cache_to_file()
    last_fetch_time = datetime.now()
    await send_admin_alert(None, "❌ خطا: کش فیلم‌ها آپدیت نشد. ممکن است ربات نتواند فیلم‌های جدیدی پیدا کند.")
    return False

async def auto_fetch_movies(context: ContextTypes.DEFAULT_TYPE):
    logger.info("شروع آپدیت خودکار کش...")
    if await fetch_movies_to_cache():
        logger.info("آپدیت خودکار کش موفق بود")
    else:
        logger.error("خطا در آپدیت خودکار کش")
        await send_admin_alert(context, "❌ خطا در آپدیت خودکار کش. لیست فیلم‌ها ممکن است قدیمی باشد.")

async def get_random_movie(max_retries=5):
    logger.info("انتخاب فیلم تصادفی...")
    for attempt in range(max_retries):
        try:
            if not cached_movies or (datetime.now() - last_fetch_time).seconds > FETCH_INTERVAL:
                logger.info("کش خالی یا قدیمی، آپدیت کش...")
                await fetch_movies_to_cache()
            
            if not cached_movies:
                logger.error("هیچ فیلمی در کش موجود نیست")
                await send_admin_alert(None, "❌ خطا: هیچ فیلمی در کش موجود نیست. لطفاً لیست را دستی آپدیت کنید.")
                return None
            
            available_movies = [m for m in cached_movies if m['id'] not in posted_movies]
            if not available_movies:
                logger.warning("هیچ فیلم جدیدی در کش نیست که قبلا پست نشده باشد. لطفاً لیست کش را آپدیت کنید.")
                await send_admin_alert(None, "⚠️ هشدار: تمام فیلم‌های موجود در کش قبلاً پست شده‌اند. برای جلوگیری از تکرار، ربات فیلم جدیدی برای پست ندارد. لطفاً لیست فیلم‌ها را با /start و 'آپدیت لیست' به‌روز کنید.")
                return None

            movie_to_process = random.choice(available_movies)
            logger.info(f"فیلم انتخاب شد: {movie_to_process['title']} (IMDb ID: {movie_to_process['id']}) (تلاش {attempt + 1})")
            
            # دریافت اطلاعات کامل فیلم (شامل خلاصه داستان و... که در مرحله کش کامل نشده)
            # و همچنین بروزرسانی امتیازات اگر از RapidAPI در کش موجود نبود
            # در اینجا movie_info اطلاعات اولیه را برمی‌گرداند، نه اطلاعات کامل کش شده از RapidAPI
            movie_info = await get_movie_info(movie_to_process['title'], movie_to_process.get('tmdb_id'))
            
            if not movie_info:
                logger.warning(f"اطلاعات اولیه فیلم {movie_to_process['title']} نامعتبر، تلاش مجدد برای انتخاب فیلم دیگر...")
                continue
            
            # --- اولویت با نمرات RapidAPI ذخیره شده در کش ---
            imdb_score_val = 0.0
            min_score = 8.0 if 'انیمیشن' in movie_info['genres'] else 6.0

            # استفاده از اطلاعات امتیاز از movie_to_process که از کش آمده
            # این شامل نمرات RapidAPI است اگر در مرحله کش گرفته شده باشد
            movie_info['imdb'] = movie_to_process['imdb'] # اطمینان از انتقال اطلاعات کامل امتیاز از کش به movie_info
            
            if movie_info['imdb'].get('imdb'):
                try:
                    # حذف " /10" از امتیاز IMDb و تبدیل به float
                    imdb_score_val = float(movie_info['imdb']['imdb'].split('/')[0])
                except ValueError:
                    logger.warning(f"فرمت امتیاز IMDb برای {movie_info['title']} نامعتبر است: {movie_info['imdb']['imdb']}. استفاده از 0.0.")
                    imdb_score_val = 0.0

            if imdb_score_val < min_score:
                logger.warning(f"فیلم {movie_to_process['title']} امتیاز {imdb_score_val} دارد، رد شد (حداقل {min_score} لازم است)")
                continue
            
            # اضافه کردن فیلم به لیست پست شده‌ها با IMDb ID
            if movie_info['imdb_id']:
                posted_movies.append(movie_info['imdb_id'])
                await save_posted_movies_to_file()
                logger.info(f"فیلم‌های ارسال‌شده: {posted_movies}")
            else:
                logger.warning(f"IMDb ID برای فیلم {movie_info['title']} یافت نشد، نمی‌توان به لیست پست‌شده‌ها اضافه کرد.")
                continue

            # ارسال امتیاز فیلم به generate_comment
            comment = await generate_comment(movie_info['genres'], imdb_score_val)
            if not comment:
                logger.error("تحلیل تولید نشد")
                continue
            
            if imdb_score_val >= 8.5:
                rating = 5
            elif 7.5 <= imdb_score_val < 8.5:
                rating = 4
            elif 6.5 <= imdb_score_val < 7.5:
                rating = 3
            elif 6.0 <= imdb_score_val < 6.5:
                rating = 2
            else:
                rating = 1
            
            if movie_info['poster']:
                if not await check_poster(movie_info['poster']):
                    movie_info['poster'] = None
            
            # انتقال تریلر از movie_to_process به movie_info
            movie_info['trailer'] = movie_to_process.get('trailer') # <-- این خط اضافه شد

            return {
                **movie_info,
                'comment': comment,
                'rating': rating,
                'special': imdb_score_val >= 8.5
            }
        except Exception as e:
            logger.error(f"خطا در انتخاب فیلم (تلاش {attempt + 1}): {str(e)}", exc_info=True)
            if attempt == max_retries - 1:
                logger.error("تلاش‌ها تمام شد، هیچ فیلمی برای پست انتخاب نشد.")
                return None
    logger.error("تلاش‌ها تمام شد، هیچ فیلمی برای پست انتخاب نشد.")
    return None

def format_movie_post(movie):
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie['special'] else ''
    channel_link = 'https://t.me/bestwatch_channel'
    rlm = '\u200F'
    genres = ' '.join([f"#{g.replace(' ', '_')}" for g in movie['genres']]) if movie['genres'] else '#سینمایی'
    
    trailer_part = ""
    # اصلاح: اطمینان از وجود کلید 'trailer' قبل از دسترسی
    if movie.get('trailer') and movie['trailer'] and movie['trailer'].startswith('http'):
        cleaned_trailer = clean_text(movie['trailer'])
        if cleaned_trailer:
            trailer_part = f" | <a href='{cleaned_trailer}'>تریلر فیلم</a>"
    
    post_sections = [
        f"""
🎬 <b>عنوان فیلم:</b>
<b>{clean_text(movie['title']) or 'بدون عنوان'}{special}</b>{trailer_part}

{genres}
📅 <b>سال تولید: {clean_text(movie['year']) or 'نامشخص'}</b> | <b>امتیاز IMDB: {clean_text(movie['imdb']['imdb']) or 'نامشخص'}</b>
"""
    ]
    
    if movie['imdb'].get('imdb_votes') and str(movie['imdb']['imdb_votes']).replace(',', '').isdigit():
        post_sections.append(f"🗳 <b>تعداد رای: {movie['imdb']['imdb_votes']}</b>\n")
    if movie['imdb'].get('rotten_tomatoes') and movie['imdb']['rotten_tomatoes'] != 'N/A':
        post_sections.append(f"🍅 <b>Rotten Tomatoes: {movie['imdb']['rotten_tomatoes']}</b>\n")
    if movie['imdb'].get('metacritic') and movie['imdb']['metacritic'] != 'N/A':
        post_sections.append(f"📊 <b>Metacritic: {movie['imdb']['metacritic']}</b>\n")
    
    if movie['plot'] and clean_text(movie['plot']) != 'متن موجود نیست':
        post_sections.append(f"""
📝 <b>خلاصه داستان:</b>
{rlm}{clean_text(movie['plot'])}...
""")
    else:
        logger.warning(f"هیچ خلاصه داستانی برای {movie['title']} موجود نیست")
    
    if movie['comment']:
        post_sections.append(f"""
🍿 <b>حرف ما:</b>
{rlm}{clean_text(movie['comment'])}
""")
    
    post_sections.append(f"""
🎯 <b>ارزش دیدن: {stars}</b>

<a href="{channel_link}">کانال بست واچ | کلیک کنید</a>
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
            InlineKeyboardButton(toggle_text, callback_data='toggle_bot') # <-- این خط اضافه شد
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
        
        async with asyncio.timeout(120):
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
        logger.error(f"خطا در post_now: {e}", exc_info=True)
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
    
    # تست RapidAPI (Movies Ratings)
    if RAPIDAPI_KEY:
        try:
            test_imdb_id = "tt0133093"  # Matrix
            ratings = await get_ratings_from_rapidapi(test_imdb_id)
            rapidapi_status = "✅ RapidAPI (Movies Ratings) اوکی" if ratings and ratings.get("imdb_rating") else f"❌ RapidAPI (Movies Ratings) خطا: {ratings}"
            results.append(rapidapi_status)
        except Exception as e:
            logger.error(f"خطا در تست RapidAPI (Movies Ratings): {str(e)}")
            results.append(f"❌ RapidAPI (Movies Ratings) خطا: {str(e)}")
    else:
        results.append("❌ RapidAPI: کلید API تنظیم نشده است.")

    # تست JobQueue
    job_queue = context.job_queue
    results.append("✅ JobQueue فعال" if job_queue else "❌ JobQueue غیرفعال")

    # تست Gemini
    if GOOGLE_API_KEY:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash') # مدل تست
            prompt_test = "تست: یک جمله به فارسی بنویس."
            response = await model.generate_content_async(prompt_test)
            text = response.text.strip()
            gemini_status = "✅ Gemini اوکی" if text and is_farsi(text) else "❌ Gemini خطا: پاسخ نامعتبر"
            results.append(gemini_status)
        except Exception as e:
            logger.error(f"خطا در تست Gemini: {str(e)}")
            api_availability['gemini'] = False
            results.append(f"❌ Gemini خطا: {str(e)}")
    else:
        results.append("❌ Gemini: کلید API تنظیم نشده است.")

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
        logger.error(f"خطا در test_all: {str(e)}", exc_info=True)
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
        logger.error(f"خطا در تست دسترسی به کانال: {str(e)}", exc_info=True)
        await msg.edit_text(f"❌ خطا در تست دسترسی به کانال: {str(e)}", reply_markup=get_tests_menu())

async def show_movies_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه show_movies")
    await query.answer()
    try:
        if not cached_movies:
            await query.message.edit_text("❌ لیست فیلم‌ها خالی است. لطفا ابتدا آن را آپدیت کنید.", reply_markup=get_main_menu())
            return
        
        movies_list = "\n".join([f"{i+1}. {m['title']} (IMDb ID: {m['id']})" for i, m in enumerate(cached_movies)])
        keyboard = [[InlineKeyboardButton("بازگشت", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if len(movies_list) > 4000:
            await query.message.edit_text("📋 لیست فیلم‌ها (بخش اول):")
            await context.bot.send_message(chat_id=query.message.chat_id, text=movies_list[:4000])
            if len(movies_list) > 4000:
                await context.bot.send_message(chat_id=query.message.chat_id, text=movies_list[4000:])
            await context.bot.send_message(chat_id=query.message.chat_id, text="...", reply_markup=reply_markup)
        else:
            await query.message.edit_text(f"📋 لیست فیلم‌ها:\n{movies_list}", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"خطا در show_movies: {str(e)}", exc_info=True)
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
        logger.error(f"خطا در toggle_bot: {str(e)}", exc_info=True)
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
        logger.error(f"خطا در ریست Webhook: {e}", exc_info=True)
        await msg.edit_text(f"❌ خطا در ریست Webhook: {str(e)}", reply_markup=get_main_menu())

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    logger.info("شروع پست خودکار...")
    try:
        if not bot_enabled:
            logger.info("پست خودکار کنسل شد: ربات غیرفعال است")
            return
        movie = await get_random_movie()
        if not movie:
            logger.error("هیچ فیلمی برای پست خودکار انتخاب نشد.")
            await send_admin_alert(context, "❌ خطا: فیلم برای پست خودکار یافت نشد. ممکن است تمام فیلم‌های کش شده قبلاً پست شده باشند یا مشکل دیگری وجود داشته باشد.")
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
        logger.error(f"خطا در ارسال پست خودکار: {e}", exc_info=True)
        await send_admin_alert(context, f"❌ خطای پست خودکار: {str(e)}")

async def health_check(request):
    return web.Response(text="OK")

async def root_handler(request):
    raise web.HTTPFound(location="https://t.me/bestwatch_channel")

async def run_web():
    logger.info(f"راه‌اندازی سرور وب روی پورت {PORT}...")
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/', root_handler)
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
    
    # ... در تابع run_bot()
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
    app.add_handler(CallbackQueryHandler(toggle_bot_handler, pattern='^toggle_bot$')) # <-- اطمینان حاصل کنید که این خط وجود دارد
    app.add_handler(CallbackQueryHandler(reset_webhook_handler, pattern='^reset_webhook$'))
# ...
    
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
    await load_cache_from_file()
    await load_posted_movies_from_file()
    
    cleaned_posted_movies = []
    for movie_id in posted_movies:
        if isinstance(movie_id, str) and movie_id.startswith('tt'):
            cleaned_posted_movies.append(movie_id)
    posted_movies[:] = cleaned_posted_movies

    if not await fetch_movies_to_cache():
        logger.error("خطا در دریافت اولیه لیست فیلم‌ها. ربات ممکن است با لیست خالی کار کند.")
    
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
        if bot_app.updater.running:
            await bot_app.updater.stop()
        if bot_app.running:
            await bot_app.stop()
        await bot_app.shutdown()
        await web_runner.cleanup()

if __name__ == '__main__':
    asyncio.run(main())
