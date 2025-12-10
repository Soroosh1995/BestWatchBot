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
from aiohttp import ClientTimeout
import urllib.parse
from datetime import datetime, timedelta
from google.api_core import exceptions as google_exceptions
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
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
PORT = int(os.getenv('PORT', 8080))
POST_INTERVAL = int(os.getenv('POST_INTERVAL', 14400)) # 4 hours in seconds
FETCH_INTERVAL = int(os.getenv('FETCH_INTERVAL', 86400)) # 24 hours in seconds

# تنظیم Gemini
if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        # استفاده از مدل gemini-2.5-flash که جدیدتر است
        GEMINI_MODEL = "gemini-2.5-flash"
    except Exception as e:
        logger.error(f"خطا در تنظیم Gemini: {e}")
        GEMINI_MODEL = None
else:
    logger.warning("GOOGLE_API_KEY تنظیم نشده است. خلاصه فیلم توسط Gemini غیرفعال است.")
    GEMINI_MODEL = None

# تنظیمات کش و دیتابیس
CACHE_FILE = "movie_cache.json"
POSTED_MOVIES_FILE = "posted_movies.json"
movie_cache = {}
posted_movies = set() # تغییر به set برای عملکرد بهتر

# ----------------- توابع ذخیره‌سازی و بارگذاری -----------------
# ... (توابع load_cache_from_file، save_cache_to_file، load_posted_movies_from_file، save_posted_movies_to_file)
async def load_cache_from_file():
    global movie_cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                movie_cache = json.load(f)
            logger.info(f"حافظه کش از فایل با {len(movie_cache)} آیتم بارگذاری شد.")
        except Exception as e:
            logger.error(f"خطا در بارگذاری حافظه کش: {e}")

async def save_cache_to_file():
    if movie_cache:
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(movie_cache, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"خطا در ذخیره حافظه کش: {e}")

async def load_posted_movies_from_file():
    global posted_movies
    if os.path.exists(POSTED_MOVIES_FILE):
        try:
            with open(POSTED_MOVIES_FILE, 'r', encoding='utf-8') as f:
                # اطمینان از تبدیل به لیست قبل از تبدیل به ست
                data = json.load(f)
                if isinstance(data, list):
                    posted_movies = set(data)
                else:
                    posted_movies = set()
            logger.info(f"لیست فیلم‌های پست شده با {len(posted_movies)} آیتم بارگذاری شد.")
        except Exception as e:
            logger.error(f"خطا در بارگذاری لیست فیلم‌های پست شده: {e}")

async def save_posted_movies_to_file():
    if posted_movies:
        try:
            with open(POSTED_MOVIES_FILE, 'w', encoding='utf-8') as f:
                # تبدیل به لیست قبل از ذخیره
                json.dump(list(posted_movies), f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"خطا در ذخیره لیست فیلم‌های پست شده: {e}")

# ----------------- توابع کمکی -----------------
# ... (توابع send_admin_alert، make_api_request، post_api_request، generate_summary)
async def send_admin_alert(bot, message):
    if ADMIN_ID and bot:
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=message
            )
        except Exception as e:
            logger.error(f"خطا در ارسال پیام ادمین: {e}")

async def make_api_request(url, params=None, headers=None, session=None, timeout=30):
    if session is None:
        session = aiohttp.ClientSession(timeout=ClientTimeout(total=timeout))
        should_close_session = True
    else:
        should_close_session = False
    
    try:
        async with session.get(url, params=params, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                logger.error(f"خطا در درخواست API به {url} (کد: {response.status}): {await response.text()}")
                return None
    except aiohttp.client_exceptions.ClientConnectorError as e:
        logger.error(f"خطای اتصال SSL/DNS در درخواست به {url}: {e}. بررسی فایل certifi.")
        return None
    except Exception as e:
        logger.error(f"خطای نامشخص در درخواست به {url}: {e}")
        return None
    finally:
        if should_close_session:
            await session.close()

async def post_api_request(url, json_data=None, headers=None, session=None, timeout=30):
    if session is None:
        session = aiohttp.ClientSession(timeout=ClientTimeout(total=timeout))
        should_close_session = True
    else:
        should_close_session = False
    
    try:
        async with session.post(url, json=json_data, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                logger.error(f"خطا در درخواست POST به {url} (کد: {response.status}): {await response.text()}")
                return None
    except Exception as e:
        logger.error(f"خطای نامشخص در درخواست POST به {url}: {e}")
        return None
    finally:
        if should_close_session:
            await session.close()


async def generate_summary(title, year):
    # ... (توابع generate_summary)
    if not GEMINI_MODEL:
        return None

    prompt = f"یک خلاصه کوتاه، جذاب و دقیق (حداکثر ۱۰۰ کلمه) درباره فیلم {title} ({year}) بنویس. فقط خلاصه فیلم را بنویس."
    
    try:
        client = genai.Client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=GEMINI_MODEL,
            contents=prompt
        )
        return response.text.strip()
    except google_exceptions.ResourceExhausted as e:
        logger.error(f"خطای اتمام منابع Gemini (ResourceExhausted): {e}")
        await send_admin_alert(None, "❌ خطا: منابع Gemini به اتمام رسیده است.")
        return "خلاصه فیلم به دلیل اتمام منابع Google Gemini موقتاً در دسترس نیست."
    except Exception as e:
        logger.error(f"خطای نامشخص در تولید خلاصه Gemini: {e}")
        return None

# ----------------- توابع دریافت فیلم‌ها -----------------
# ... (توابع get_movie_details_omdb_rapid، get_movie_details_tmdb)
async def get_movie_details_tmdb(movie_id):
    # ...
    # API call to TMDB
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY تنظیم نشده است.")
        return None

    # آدرس API: https://api.themoviedb.org/3/movie/
    url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    headers = {
        "Authorization": f"Bearer {TMDB_API_KEY}",
        "accept": "application/json"
    }

    data = await make_api_request(url, headers=headers)
    if not data:
        return None

    # دریافت جزئیات اضافی (مثل بازیگران)
    credits_url = f"https://api.themoviedb.org/3/movie/{movie_id}/credits"
    credits_data = await make_api_request(credits_url, headers=headers)
    
    # ... (استخراج بازیگران)
    
    # ساخت دیکشنری نهایی
    details = {
        'id': data.get('id'),
        'imdb_id': data.get('imdb_id'),
        'title': data.get('title'),
        'original_title': data.get('original_title'),
        'release_date': data.get('release_date'),
        'year': data.get('release_date', '----')[:4],
        'runtime': data.get('runtime'),
        'overview': data.get('overview'),
        'genres': [g.get('name') for g in data.get('genres', [])],
        'poster_path': data.get('poster_path'),
        'vote_average': data.get('vote_average'),
        'vote_count': data.get('vote_count'),
        'tagline': data.get('tagline'),
        'cast': cast_list, # لیست بازیگران استخراج شده
        'directors': director_list,
        'writers': writer_list
    }
    
    return details


async def get_movie_details_omdb_rapid(imdb_id):
    # ...
    # API call to OMDB and RapidAPI
    if not OMDB_API_KEY and not RAPIDAPI_KEY:
        logger.error("OMDB_API_KEY و RAPIDAPI_KEY تنظیم نشده‌اند.")
        return None

    details = {}
    
    # مرحله ۱: تماس با OMDB API
    if OMDB_API_KEY:
        omdb_url = f"http://www.omdbapi.com/?i={imdb_id}&apikey={OMDB_API_KEY}"
        omdb_data = await make_api_request(omdb_url)
        
        if omdb_data and omdb_data.get('Response') == 'True':
            details.update({
                'rated': omdb_data.get('Rated'),
                'plot': omdb_data.get('Plot'),
                'language': omdb_data.get('Language'),
                'country': omdb_data.get('Country'),
                'awards': omdb_data.get('Awards'),
                'metascore': omdb_data.get('Metascore'),
                'imdb_rating': omdb_data.get('imdbRating'),
                'imdb_votes': omdb_data.get('imdbVotes'),
                'box_office': omdb_data.get('BoxOffice'),
                'production': omdb_data.get('Production'),
                'website': omdb_data.get('Website'),
                'director': omdb_data.get('Director'),
                'writer': omdb_data.get('Writer'),
                'actors': omdb_data.get('Actors'),
            })

    # مرحله ۲: تماس با RapidAPI (اگر OMDB اطلاعات کافی نداد یا اگر نیاز به امتیازهای دیگر داریم)
    # این بخش باید بر اساس نیاز پروژه شما و اینکه RapidAPI شما چیست، سفارشی شود.
    # به دلیل عدم اطلاع از سرویس دقیق RapidAPI، این بخش را فقط برای مثال نگه می‌داریم:
    if RAPIDAPI_KEY and not details.get('imdb_rating'):
        rapidapi_url = f"https://movie-details-by-imdb-id.p.rapidapi.com/movie/{imdb_id}"
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "movie-details-by-imdb-id.p.rapidapi.com"
        }
        rapid_data = await make_api_request(rapidapi_url, headers=headers)
        
        if rapid_data and rapid_data.get('status') == 'OK':
            # مثال: اضافه کردن داده‌های RapidAPI
            details['rapid_rating'] = rapid_data.get('rating')
            # ...
            pass # شما باید اینجا منطق ادغام داده‌ها را بنویسید

    return details

async def get_movie_id_from_tmdb(title, year):
    # ... (توابع get_movie_id_from_tmdb)
    # API call to TMDB search
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY تنظیم نشده است.")
        return None

    # آدرس API: https://api.themoviedb.org/3/search/movie
    url = "https://api.themoviedb.org/3/search/movie"
    headers = {
        "Authorization": f"Bearer {TMDB_API_KEY}",
        "accept": "application/json"
    }
    params = {
        "query": title,
        "primary_release_year": year,
        "language": "en-US"
    }

    data = await make_api_request(url, params=params, headers=headers)
    if data and data.get('results'):
        # گرفتن دقیق‌ترین نتیجه
        return data['results'][0].get('id')
    return None

async def fetch_movies_to_cache():
    # ... (توابع fetch_movies_to_cache)
    # API call to fetch a list of top movies (e.g., TMDB top rated or popular)
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY تنظیم نشده است.")
        return False
        
    url = "https://api.themoviedb.org/3/discover/movie"
    headers = {
        "Authorization": f"Bearer {TMDB_API_KEY}",
        "accept": "application/json"
    }
    
    # پارامترهای دیسکاور (می‌توانید اینجا فیلترهای دلخواه خود را اعمال کنید)
    params = {
        "include_adult": "false",
        "include_video": "false",
        "language": "en-US",
        "sort_by": "vote_average.desc",
        "vote_count.gte": 1000, # حداقل تعداد رای
        "page": 1,
        # فیلتر برای فیلم‌های اخیر (مثلاً ۱۰ سال گذشته)
        "primary_release_date.gte": (datetime.now() - timedelta(days=365*10)).strftime('%Y-%m-%d')
    }
    
    global movie_cache
    new_movie_ids = set()
    total_pages = 5 # تعداد صفحاتی که می‌خواهید بررسی کنید
    
    async with aiohttp.ClientSession(timeout=ClientTimeout(total=60)) as session:
        for page in range(1, total_pages + 1):
            params['page'] = page
            data = await make_api_request(url, params=params, headers=headers, session=session)
            
            if data and data.get('results'):
                for movie in data['results']:
                    tmdb_id = movie.get('id')
                    imdb_id = movie.get('imdb_id') # TMDB در دیسکاور imdb_id را نمی‌دهد، باید جداگانه دریافت شود
                    
                    if tmdb_id not in movie_cache and tmdb_id not in posted_movies:
                        new_movie_ids.add(tmdb_id)
            else:
                logger.warning(f"دریافت صفحه {page} ناموفق بود.")
                break # اگر یک صفحه ناموفق بود، صفحات بعدی را چک نکنید

        # در اینجا باید جزئیات کامل و imdb_id را برای هر فیلم جدید دریافت کنید
        for tmdb_id in new_movie_ids:
            if tmdb_id not in movie_cache:
                details = await get_movie_details_tmdb(tmdb_id)
                if details and details.get('imdb_id'):
                    omdb_rapid_details = await get_movie_details_omdb_rapid(details['imdb_id'])
                    
                    # ادغام داده‌ها
                    final_details = {**details, **omdb_rapid_details} 
                    movie_cache[tmdb_id] = final_details
                    logger.info(f"فیلم جدید به کش اضافه شد: {details['title']}")
    
    await save_cache_to_file()
    return len(movie_cache) > 0

# ----------------- توابع تلگرام -----------------
# ... (توابع build_movie_caption، start، post_movie_job، run_bot)
def build_movie_caption(details, summary):
    # ...
    # ساخت کپشن فیلم
    
    # جایگزینی‌های لازم
    imdb_id = details.get('imdb_id', 'N/A')
    
    caption = f"🎬 **{details.get('title')}** ({details.get('year')})\n\n"
    caption += f"✨ خلاصه: {summary}\n" if summary else ""
    caption += f"⭐ امتیاز IMDb: {details.get('imdb_rating', 'N/A')} ({details.get('imdb_votes', 'N/A')} رای)\n"
    caption += f"🍅 امتیاز Metascore: {details.get('metascore', 'N/A')}\n"
    caption += f"⏱ مدت زمان: {details.get('runtime', 'N/A')} دقیقه\n"
    caption += f"🎭 ژانر: {', '.join(details.get('genres', []))}\n"
    caption += f"👥 بازیگران: {details.get('actors', 'N/A')}\n"
    caption += f"🎬 کارگردان: {details.get('director', 'N/A')}\n"
    caption += f"🌎 کشور: {details.get('country', 'N/A')}\n"
    caption += f"🏅 جوایز: {details.get('awards', 'N/A')}\n\n"
    
    # دکمه
    keyboard = [[
        InlineKeyboardButton("مشاهده تریلر و جزئیات بیشتر", url=f"https://www.imdb.com/title/{imdb_id}/")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    return caption, reply_markup

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == int(ADMIN_ID):
        await update.message.reply_text(
            "به ربات BestWatch خوش آمدید. برای شروع /post را بزنید یا منتظر اجرای خودکار بمانید."
        )
    else:
        await update.message.reply_text("شما ادمین نیستید.")

async def post_movie_job(context: ContextTypes.DEFAULT_TYPE):
    # ... (توابع post_movie_job)
    bot = context.bot
    
    if not movie_cache:
        logger.warning("کش فیلم‌ها خالی است. تلاش برای دریافت مجدد...")
        if not await fetch_movies_to_cache():
            await send_admin_alert(bot, "⚠️ کش فیلم‌ها خالی است و دریافت مجدد ناموفق بود.")
            return

    # انتخاب تصادفی
    available_movies = [id for id in movie_cache.keys() if id not in posted_movies]
    
    if not available_movies:
        logger.warning("تمام فیلم‌های موجود پست شده‌اند. کش را ریست می‌کنیم.")
        await send_admin_alert(bot, "🔄 تمام فیلم‌های موجود در کش پست شدند. ریست کردن کش فیلم‌های پست شده.")
        posted_movies.clear()
        available_movies = list(movie_cache.keys())
        await save_posted_movies_to_file()
        
        if not available_movies:
            logger.error("کش کاملاً خالی است حتی پس از ریست.")
            await send_admin_alert(bot, "❌ کش فیلم‌ها کاملاً خالی است.")
            return

    chosen_id = random.choice(available_movies)
    details = movie_cache.get(chosen_id)
    
    if not details or not details.get('poster_path'):
        logger.error(f"جزئیات فیلم انتخاب شده {chosen_id} ناقص است. حذف و ادامه.")
        del movie_cache[chosen_id]
        await save_cache_to_file()
        return

    # تولید خلاصه
    summary = await generate_summary(details['title'], details['year'])

    # ساخت کپشن و دکمه
    caption, reply_markup = build_movie_caption(details, summary)
    
    # ارسال پیام
    try:
        poster_url = f"https://image.tmdb.org/t/p/original{details['poster_path']}"
        
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=poster_url,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        posted_movies.add(chosen_id)
        del movie_cache[chosen_id] # حذف از کش بعد از پست شدن
        await save_posted_movies_to_file()
        await save_cache_to_file()
        logger.info(f"فیلم {details['title']} با موفقیت پست شد.")
        
    except telegram.error.BadRequest as e:
        logger.error(f"خطای ارسال تلگرام (احتمالاً کپشن طولانی یا عکس نامعتبر): {e}")
        await send_admin_alert(bot, f"❌ خطا در ارسال فیلم {details['title']}: {e}")
    except Exception as e:
        logger.error(f"خطای نامشخص در ارسال: {e}")
        await send_admin_alert(bot, f"❌ خطای نامشخص در ارسال فیلم {details['title']}: {e}")


async def run_bot():
    """راه‌اندازی بات و زمان‌بندی کارها"""
    if not TELEGRAM_TOKEN or not CHANNEL_ID or not ADMIN_ID:
        logger.error("کلیدهای ضروری (TOKEN, CHANNEL_ID, ADMIN_ID) تنظیم نشده‌اند.")
        return None

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # زمان‌بندی کارها (Long Polling)
    application.job_queue.run_repeating(post_movie_job, interval=POST_INTERVAL, first=10) # اولین اجرا بعد از 10 ثانیه
    application.job_queue.run_repeating(
        lambda context: asyncio.create_task(fetch_movies_to_cache()), 
        interval=FETCH_INTERVAL
    )

    # هندلرهای کامند
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("post", post_movie_job)) # اجرای دستی برای ادمین

    # راه‌اندازی Long Polling
    await application.start()
    await application.updater.start_polling()
    logger.info("بات با Long Polling شروع به کار کرد.")
    
    return application

async def main():
    logger.info("شروع برنامه...")
    await load_cache_from_file()
    await load_posted_movies_from_file()
    
    # تمیزکاری posted_movies (حذف داده‌های غیرضروری)
    cleaned_posted_movies = set()
    for movie_id in posted_movies:
        if isinstance(movie_id, str) and movie_id.startswith(('tt', '2')): # فرض: tmdb_id عددی و imdb_id با tt شروع می‌شود
            cleaned_posted_movies.add(movie_id)
    posted_movies.clear()
    posted_movies.update(cleaned_posted_movies)

    if not await fetch_movies_to_cache():
        logger.error("خطا در دریافت اولیه لیست فیلم‌ها. ربات ممکن است با لیست خالی کار کند.")
    
    # حذف Webhook قدیمی (فقط برای اطمینان در اجرای اول)
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
        # await send_admin_alert(None, f"❌ خطا در ریست Webhook اولیه: {str(e)}") # حذف هشدار به ادمین در اجرای اولیه

    # راه‌اندازی بات
    bot_app = await run_bot()
    
    try:
        # منتظر ماندن برای اجرای بی‌نهایت
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("خاموش کردن بات...")
    finally:
        if bot_app and bot_app.updater and bot_app.updater.running:
            await bot_app.updater.stop()
        if bot_app and bot_app.running:
            await bot_app.stop()
        if bot_app:
            await bot_app.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
