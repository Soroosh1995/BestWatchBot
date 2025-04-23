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

# تنظیمات اولیه
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

# وضعیت دسترسی APIها
api_availability = {
    'gemini': True,
    'groq': True,
    'openai': True
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
        'فیلم پر از پیچش‌های داستانیه، ولی ریتمش گاهی افت می‌کنه. شخصیت‌ها متوسطه، اما کارگردانی هیجان‌انگیزه. موسیقی متن به فضا جون می‌ده. حس و حالش تو رو کنجکاو نگه می‌داره.',
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

# شمارشگر خطاهای API
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
async def get_imdb_id(tmdb_movie_id):
    url = f"https://api.themoviedb.org/3/movie/{tmdb_movie_id}/external_ids?api_key={TMDB_API_KEY}"
    data = await make_api_request(url)
    if data and data.get("imdb_id"):
        return data["imdb_id"]  # مثلاً: tt1234567
    logger.warning(f"هیچ IMDb ID برای TMDB ID {tmdb_movie_id} یافت نشد")
    return None

# تابع برای گرفتن نمرات از RapidAPI
async def get_ratings_from_rapidapi(imdb_id):
    logger.info(f"درخواست به RapidAPI با IMDb ID: {imdb_id}")
    if not imdb_id or not isinstance(imdb_id, str) or not imdb_id.startswith("tt"):
        logger.error(f"IMDb ID نامعتبر: {imdb_id}")
        return None
    
    url = "https://movies-ratings2.p.rapidapi.com/ratings"
    headers = {
        "X-RapidAPI-Key": os.getenv("RAPIDAPI_KEY"),
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
    
    # 1. Groq
    if api_availability['groq']:
        logger.info("تلاش با Groq برای ترجمه")
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
                        {"role": "system", "content": "Translate the movie plot from English to Persian accurately and concisely. Use only Persian."},
                        {"role": "user", "content": f"Translate: {plot}"}
                    ],
                    "max_tokens": 150,
                    "temperature": 0.5
                }
                response = await post_api_request(url, data, headers, retries=3)
                if response and response.get('choices'):
                    translated_plot = clean_text_for_validation(response['choices'][0]['message']['content'].strip())
                    if is_valid_plot(translated_plot) and is_farsi(translated_plot):
                        logger.info(f"ترجمه Groq موفق برای {title}: {translated_plot[:100]}...")
                        return translated_plot
                    logger.warning(f"ترجمه Groq نامعتبر برای {title}: {translated_plot}")
                else:
                    logger.warning(f"پاسخ Groq خالی یا نامعتبر برای ترجمه: {response}")
        except Exception as e:
            logger.error(f"خطا در ترجمه Groq برای {title}: {str(e)}")
            api_availability['groq'] = False
            await send_admin_alert(None, f"❌ خطا در ترجمه Groq: {str(e)}.")

    # 2. Gemini
    if api_availability['gemini']:
        logger.info("تلاش با Gemini برای ترجمه")
        try:
            async with asyncio.timeout(15):
                model = genai.GenerativeModel('gemini-2.0-flash')
                prompt = f"خلاصه داستان فیلم را از انگلیسی به فارسی ترجمه کن. ترجمه باید دقیق و مناسب برای خلاصه فیلم باشد. فقط از فارسی استفاده کن: {plot}"
                response = await model.generate_content_async(prompt)
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
    tmdb_movie_id = movie.get('id')
    
    # گرفتن IMDb ID
    imdb_id = await get_imdb_id(tmdb_movie_id)
    
    # بررسی ژانرها
    is_animation = False
    if genres:
        is_animation = 'انیمیشن' in genres
    else:
        details_url = f"https://api.themoviedb.org/3/movie/{tmdb_movie_id}?api_key={TMDB_API_KEY}&language=en-US"
        details_data = await make_api_request(details_url)
        genres = [GENRE_TRANSLATIONS.get(g['name'], 'سایر') for g in details_data.get('genres', [])]
        is_animation = 'انیمیشن' in genres
    
    min_score = 8.0 if is_animation else 6.0
    
    # 1. RapidAPI
    if imdb_id:
        ratings = await get_ratings_from_rapidapi(imdb_id)
        if ratings and ratings.get("imdb_rating"):
            imdb_score = float(ratings["imdb_rating"])
            if imdb_score < min_score:
                logger.warning(f"فیلم {title} امتیاز {imdb_score} دارد، رد شد (حداقل {min_score} لازم است)")
                return None
            api_errors['tmdb'] = 0
            return {
                "imdb": f"{imdb_score:.1f}/10",
                "imdb_votes": ratings.get("imdb_votes"),
                "rotten_tomatoes": ratings.get("rotten_tomatoes"),
                "metacritic": ratings.get("metacritic")
            }
    
    # 2. TMDB (فال‌بک)
    imdb_score = movie.get('vote_average', 0)
    if imdb_score < min_score:
        logger.warning(f"فیلم {title} امتیاز {imdb_score} دارد، رد شد (حداقل {min_score} لازم است)")
        return None
    api_errors['tmdb'] = 0
    return {
        "imdb": f"{float(imdb_score):.1f}/10",
        "imdb_votes": movie.get("vote_count"),
        "rotten_tomatoes": None,
        "metacritic": None
    }

async def get_imdb_score_omdb(title, genres=None):
    logger.info(f"دریافت اطلاعات OMDb برای: {title}")
    encoded_title = urllib.parse.quote(title)
    url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_title}&type=movie"
    data = await make_api_request(url)
    if not data or data.get('Response') == 'False':
        logger.warning(f"OMDb هیچ نتیجه‌ای برای {title} نداد: {data.get('Error')}")
        api_errors['omdb'] += 1
        return None
    
    is_animation = False
    if genres:
        is_animation = 'انیمیشن' in genres
    else:
        genres = data.get('Genre', '').split(', ')
        genres = [GENRE_TRANSLATIONS.get(g.strip(), 'سایر') for g in genres]
        is_animation = 'انیمیشن' in genres
    
    min_score = 8.0 if is_animation else 6.0
    imdb_score = data.get('imdbRating', '0')
    
    if float(imdb_score) < min_score:
        logger.warning(f"فیلم {title} امتیاز {imdb_score} دارد، رد شد (حداقل {min_score} لازم است)")
        return None
    api_errors['omdb'] = 0
    return {
        "imdb": f"{float(imdb_score):.1f}/10",
        "imdb_votes": data.get("imdbVotes"),
        "rotten_tomatoes": None,
        "metacritic": None
    }
    
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
        
        if 'مستند' in genres:
            logger.warning(f"فیلم {tmdb_title} مستند است، رد شد")
            return None
        
        # تلاش برای خلاصه داستان فارسی
        search_url_fa = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=fa-IR"
        tmdb_data_fa = await make_api_request(search_url_fa)
        tmdb_plot = tmdb_data_fa['results'][0].get('overview', '') if tmdb_data_fa.get('results') else ''
        logger.info(f"خلاصه داستان TMDB (فارسی) برای {tmdb_title}: {tmdb_plot[:100]}...")
        
        if tmdb_plot and is_farsi(tmdb_plot) and is_valid_plot(tmdb_plot):
            logger.info(f"خلاصه داستان فارسی معتبر برای {tmdb_title}")
            plot = shorten_plot(tmdb_plot)
        else:
            logger.warning(f"خلاصه داستان TMDB غیرفارسی یا نامعتبر برای {tmdb_title}: {tmdb_plot}")
            tmdb_plot_en = movie.get('overview', '')
            logger.info(f"خلاصه داستان TMDB (انگلیسی) برای {tmdb_title}: {tmdb_plot_en[:100]}...")
            if tmdb_plot_en:
                translated_plot = await translate_plot(tmdb_plot_en, tmdb_title)
                if translated_plot:
                    plot = shorten_plot(translated_plot)
                else:
                    logger.error(f"ترجمه خلاصه داستان برای {tmdb_title} ناموفق بود")
                    return None
            else:
                logger.error(f"هیچ خلاصه داستان انگلیسی برای {tmdb_title} یافت نشد")
                return None
        
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
            return None
        
        previous_plots.append(plot)
        if len(previous_plots) > 10:
            previous_plots.pop(0)
        
        return {
            'title': tmdb_title,
            'year': tmdb_year,
            'plot': plot,
            'imdb': imdb_score,  # حالا شامل تمام نمرات
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
        
        if 'مستند' in genres:
            logger.warning(f"فیلم {omdb_data.get('Title')} مستند است، رد شد")
            return None
        
        imdb_score = await get_imdb_score_omdb(omdb_data.get('Title', title), genres)
        if not imdb_score:
            logger.warning(f"امتیاز معتبر برای {omdb_data.get('Title', title)} یافت نشد")
            return None
        
        plot = omdb_data.get('Plot', '')
        logger.info(f"خلاصه داستان OMDb برای {omdb_data.get('Title', title)}: {plot[:100]}...")
        if plot and is_farsi(plot) and is_valid_plot(plot):
            logger.info(f"خلاصه داستان فارسی معتبر برای {omdb_data.get('Title', title)}")
            plot = shorten_plot(plot)
        else:
            logger.warning(f"خلاصه داستان OMDb غیرفارسی یا نامعتبر برای {omdb_data.get('Title', title)}: {plot}")
            translated_plot = await translate_plot(plot, omdb_data.get('Title', title))
            if translated_plot:
                plot = shorten_plot(translated_plot)
            else:
                logger.error(f"ترجمه خلاصه داستان برای {omdb_data.get('Title', title)} ناموفق بود")
                return None
        
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
    return None

async def generate_comment(genres):
    logger.info("تولید تحلیل...")
    logger.info(f"وضعیت APIها: Gemini={api_availability['gemini']}, Groq={api_availability['groq']}, OpenAI={api_availability['openai']}")

    # انتخاب ژانر برای فال‌بک
    selected_genre = None
    for genre in genres:
        if genre in FALLBACK_COMMENTS:
            selected_genre = genre
            break
    if not selected_genre:
        selected_genre = 'سایر'
    logger.info(f"ژانر انتخاب‌شده برای تحلیل/فال‌بک: {selected_genre}")

    # پرامپت جدید
    prompt = """یک تحلیل به زبان فارسی درباره فیلم بنویس. تحلیل باید به جنبه‌های مختلف فیلم اشاره کند و نقاط قوت و ضعف احتمالی آن را نیز در نظر بگیرد و به معرفی فیلم بپردازد. از زبان ساده و روان استفاده کن. متن بین 50 تا 80 کلمه و شامل 4 تا 6 جمله کوتاه و کامل باشد و جمله آخر، یک جمع‌بندی کلی و واقع‌بینانه از تجربه تماشای فیلم ارائه دهد. از ذکر نام فیلم یا بازیگر و تشبیهات بسیار اغراق‌آمیز خودداری کن."""

    # 1. Gemini
    if api_availability['gemini']:
        logger.info("تلاش با Gemini")
        try:
            async with asyncio.timeout(15):
                model = genai.GenerativeModel('gemini-2.0-flash')
                response = await model.generate_content_async(prompt)
                text = clean_text_for_validation(response.text.strip())
                if is_valid_comment(text):
                    previous_comments.append(text)
                    if len(previous_comments) > 10:
                        previous_comments.pop(0)
                    logger.info("تحلیل Gemini با موفقیت دریافت شد")
                    return text.rstrip('.')
                logger.warning(f"تحلیل Gemini نامعتبر: {text}")
                shortened_text = shorten_comment(text)
                if shortened_text:
                    previous_comments.append(shortened_text)
                    if len(previous_comments) > 10:
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
                        {"role": "system", "content": "You are a movie enthusiast writing in Persian with a sincere and engaging tone."},
                        {"role": "user", "content": prompt}
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
                        return text.rstrip('.')
                    logger.warning(f"تحلیل Groq نامعتبر: {text}")
                    shortened_text = shorten_comment(text)
                    if shortened_text:
                        previous_comments.append(shortened_text)
                        if len(previous_comments) > 10:
                            previous_comments.pop(0)
                        logger.info("تحلیل Groq کوتاه‌شده با موفقیت دریافت شد")
                        return shortened_text.rstrip('.')
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
                        {"role": "system", "content": "You are a movie enthusiast writing in Persian with a sincere and engaging tone."},
                        {"role": "user", "content": prompt}
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
                    return text.rstrip('.')
                logger.warning(f"تحلیل Open AI نامعتبر: {text}")
                shortened_text = shorten_comment(text)
                if shortened_text:
                    previous_comments.append(shortened_text)
                    if len(previous_comments) > 10:
                        previous_comments.pop(0)
                    logger.info("تحلیل Open AI کوتاه‌شده با موفقیت دریافت شد")
                    return shortened_text.rstrip('.')
        except Exception as e:
            logger.error(f"خطا در Open AI API: {str(e)}")
            api_availability['openai'] = False
            await send_admin_alert(None, f"❌ خطا در Open AI: {str(e)}.")

    # 4. فال‌بک موقت
    logger.warning(f"هیچ تحلیلگری در دسترس نیست، استفاده از فال‌بک موقت برای ژانر {selected_genre}")
    fallback_comment = random.choice(FALLBACK_COMMENTS[selected_genre])
    if is_valid_comment(fallback_comment):
        previous_comments.append(fallback_comment)
        if len(previous_comments) > 10:
            previous_comments.pop(0)
        logger.info(f"تحلیل فال‌بک با موفقیت استفاده شد: {fallback_comment}")
        await send_admin_alert(None, f"⚠️ هشدار: تحلیل با فال‌بک تولید شد (ژانر: {selected_genre}). لطفاً APIها را بررسی کنید.")
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
    new_movies = []
    for attempt in range(5):
        try:
            async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as session:
                page = 1
                while len(new_movies) < 100 and page <= 20:
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
                            details_url = f"https://api.themoviedb.org/3/movie/{m.get('id')}?api_key={TMDB_API_KEY}&language=en-US"
                            details_data = await make_api_request(details_url)
                            if not details_data:
                                logger.warning(f"جزئیات TMDB برای {m['title']} دریافت نشد")
                                continue
                            genres = [GENRE_TRANSLATIONS.get(g['name'], 'سایر') for g in details_data.get('genres', [])]
                            if 'مستند' in genres:
                                logger.info(f"فیلم {m['title']} مستند است، رد شد")
                                continue
                            imdb_score = await get_imdb_score_tmdb(m['title'])
                            if imdb_score and float(imdb_score['imdb'].split('/')[0]) >= 6.0:
                                new_movies.append({'title': m['title'], 'id': str(m['id'])})
                            else:
                                logger.info(f"فیلم {m['title']} امتیاز کافی ندارد")
                        page += 1

                    logger.info(f"تلاش با OMDb برای کش، صفحه {page}")
                    omdb_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&s=movie&type=movie&page={page}"
                    omdb_data = await make_api_request(omdb_url)
                    if omdb_data and omdb_data.get('Search'):
                        for m in omdb_data['Search']:
                            if not (m.get('Title') and m.get('imdbID')):
                                logger.warning(f"فیلم OMDb بدون اطلاعات کافی: {m}")
                                continue
                            genres = m.get('Genre', '').split(', ')
                            genres = [GENRE_TRANSLATIONS.get(g.strip(), 'سایر') for g in genres]
                            if 'مستند' in genres:
                                logger.info(f"فیلم {m['Title']} مستند است، رد شد")
                                continue
                            imdb_score = await get_imdb_score_omdb(m['Title'])
                            if imdb_score and float(imdb_score['imdb'].split('/')[0]) >= 6.0:
                                new_movies.append({'title': m['Title'], 'id': m['imdbID']})
                            else:
                                logger.info(f"فیلم {m['Title']} امتیاز کافی ندارد")
                        page += 1
                
                if new_movies:
                    cached_movies = new_movies[:100]
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
    await send_admin_alert(None, "❌ خطا: کش فیلم‌ها آپدیت نشد")
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
                logger.error("هیچ فیلمی در کش موجود نیست")
                return None
            
            available_movies = [m for m in cached_movies if m['id'] not in posted_movies]
            if not available_movies:
                logger.warning("هیچ فیلم جدیدی در کش نیست، ریست لیست پست‌شده‌ها")
                posted_movies.clear()
                await save_posted_movies_to_file()
                available_movies = cached_movies
            
            movie = random.choice(available_movies)
            logger.info(f"فیلم انتخاب شد: {movie['title']} (تلاش {attempt + 1})")
            movie_info = await get_movie_info(movie['title'])
            if not movie_info or movie_info['imdb']['imdb'] == '0.0/10':
                logger.warning(f"اطلاعات فیلم {movie['title']} نامعتبر، تلاش مجدد...")
                continue
            
            if 'انیمیشن' in movie_info['genres'] and float(movie_info['imdb']['imdb'].split('/')[0]) < 8.0:
                logger.warning(f"فیلم {movie['title']} انیمیشن است اما امتیاز {movie_info['imdb']['imdb']} دارد، رد شد")
                continue
            
            posted_movies.append(movie['id'])
            await save_posted_movies_to_file()
            logger.info(f"فیلم‌های ارسال‌شده: {posted_movies}")
            comment = await generate_comment(movie_info['genres'])
            if not comment:
                logger.error("تحلیل تولید نشد")
                continue
            
            imdb_score = float(movie_info['imdb']['imdb'].split('/')[0])
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
                logger.error("تلاش‌ها تمام شد")
                return None
    logger.error("تلاش‌ها تمام شد")
    return None

def format_movie_post(movie):
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie['special'] else ''
    channel_link = 'https://t.me/bestwatch_channel'
    rlm = '\u200F'
    genres = ' '.join([f"#{g.replace(' ', '_')}" for g in movie['genres']]) if movie['genres'] else '#سینمایی'
    
    trailer_part = f" | <a href='{clean_text(movie['trailer'])}'>تریلر فیلم</a>" if movie['trailer'] and movie['trailer'].startswith('http') else ""
    
    post_sections = [
        f"""
🎬 <b>عنوان فیلم:</b>
<b>{clean_text(movie['title']) or 'بدون عنوان'}{special}</b>{trailer_part}

{genres}
📅 <b>سال تولید: {clean_text(movie['year']) or 'نامشخص'}</b> | <b>امتیاز IMDB: {clean_text(movie['imdb']['imdb']) or 'نامشخص'}</b>
"""
    ]
    
    if movie['imdb'].get('imdb_votes'):
        post_sections.append(f"🗳 <b>تعداد رای: {movie['imdb']['imdb_votes']}</b>\n")
    if movie['imdb'].get('rotten_tomatoes'):
        post_sections.append(f"🍅 <b>Rotten Tomatoes: {movie['imdb']['rotten_tomatoes']}</b>\n")
    if movie['imdb'].get('metacritic'):
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

    # تست RapidAPI
    try:
        test_imdb_id = "tt0133093"  # Matrix
        ratings = await get_ratings_from_rapidapi(test_imdb_id)
        rapidapi_status = "✅ RapidAPI اوکی" if ratings and ratings.get("imdb_rating") else f"❌ RapidAPI خطا: {ratings}"
        results.append(rapidapi_status)
    except Exception as e:
        logger.error(f"خطا در تست RapidAPI: {str(e)}")
        results.append(f"❌ RapidAPI خطا: {str(e)}")

    # تست JobQueue
    job_queue = context.job_queue
    results.append("✅ JobQueue فعال" if job_queue else "❌ JobQueue غیرفعال")

    # تست Gemini
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
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

async def root_handler(request):
    raise web.HTTPFound(location="https://t.me/bestwatch_channel")  # ریدایرکت به کانال

async def run_web():
    logger.info(f"راه‌اندازی سرور وب روی پورت {PORT}...")
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/', root_handler)  # مسیر ریشه با ریدایرکت
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
    await init_openai_client()
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
