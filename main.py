import telegram
import asyncio
import os
import logging
import aiohttp
import random
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from aiohttp import web
import re
import urllib.parse
from datetime import datetime, time, timedelta

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
PORT = int(os.getenv('PORT', 8080))

# تنظیم Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# --- کش فیلم‌ها، پست‌شده‌ها و متن‌های قبلی ---
cached_movies = []
posted_movies = []
last_fetch_time = None
previous_plots = []
previous_comments = []

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
    'Science Fiction': 'علمی-تخیلی',
    'Thriller': 'هیجان‌انگیز',
    'War': 'جنگی',
    'Western': 'وسترن'
}

# --- فیلم پیش‌فرض برای فال‌بک ---
FALLBACK_MOVIE = {
    'title': 'Inception',
    'year': '2010',
    'plot': 'دزدی که اسرار شرکت‌ها را با فناوری رویا می‌دزدد، باید ایده‌ای در ذهن یک مدیر بکارد. گذشته غم‌انگیز او ممکن است پروژه را به فاجعه بکشاند.',
    'imdb': '8.8/10',
    'trailer': 'https://www.youtube.com/watch?v=YoHD9XEInc0',
    'poster': 'https://m.media-amazon.com/images/M/MV5BMjAxMzY3NjcxNF5BMl5BanBnXkFtZTcwNTI5OTM0Mw@@._V1_SX300.jpg',
    'comment': 'این فیلم اثری جذاب در ژانر علمی-تخیلی است که با داستانی پیچیده و جلوه‌های بصری خیره‌کننده، ذهن را به چالش می‌کشد. بازیگری و کارگردانی بی‌نقص، آن را فراموش‌نشدنی کرده‌اند. تنها ضعف، ریتم کند برخی صحنه‌هاست.',
    'rating': 4,
    'special': True,
    'genres': ['علمی-تخیلی', 'هیجان‌انگیز']
}

# --- حالت‌های ConversationHandler ---
ADD_MOVIE_TITLE = 1

# --- توابع کمکی ---
def clean_text(text):
    """پاکسازی متن بدون اسکیپ برای HTML"""
    if not text or text == 'N/A':
        return "متن موجود نیست"
    return text[:300]

def shorten_plot(text, max_sentences=3):
    """کوتاه کردن خلاصه داستان به 2-3 جمله کامل"""
    sentences = [s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟']
    return '. '.join(sentences[:max_sentences]) + ('.' if sentences else '')

def is_farsi(text):
    """چک کردن فارسی بودن متن"""
    farsi_chars = r'[\u0600-\u06FF]'
    return bool(re.search(farsi_chars, text))

def is_valid_plot(text):
    """چک کردن معتبر بودن خلاصه داستان"""
    if not text or len(text.split()) < 5 or text in previous_plots:
        return False
    sentences = text.split('. ')
    return len([s for s in sentences if s.strip() and s.strip()[-1] in '.!؟']) >= 1

async def get_movie_info(title):
    """دریافت اطلاعات فیلم از TMDB با فیلترهای دقیق"""
    logger.info(f"دریافت اطلاعات برای فیلم: {title}")
    try:
        async with aiohttp.ClientSession() as session:
            # جستجو برای عنوان انگلیسی
            encoded_title = urllib.parse.quote(title)
            search_url_en = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=en-US"
            async with session.get(search_url_en) as tmdb_response_en:
                tmdb_data_en = await tmdb_response_en.json()
                if not tmdb_data_en.get('results'):
                    logger.warning(f"TMDB هیچ نتیجه‌ای برای {title} (انگلیسی) نداد")
                    return None
                movie = tmdb_data_en['results'][0]
                movie_id = movie.get('id')
                tmdb_title = movie.get('title', title)
                tmdb_poster = f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else None
            
            # جستجو برای اطلاعات فارسی
            search_url_fa = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=fa-IR"
            async with session.get(search_url_fa) as tmdb_response_fa:
                tmdb_data_fa = await tmdb_response_fa.json()
                tmdb_plot = tmdb_data_fa['results'][0].get('overview', '') if tmdb_data_fa.get('results') else ''
                tmdb_year = tmdb_data_fa['results'][0].get('release_date', 'N/A')[:4] if tmdb_data_fa.get('results') else 'N/A'
            
            # دریافت ژانرها و امتیاز
            details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
            async with session.get(details_url) as details_response:
                details_data = await details_response.json()
                imdb_score = details_data.get('vote_average', 0)
                if imdb_score < 5.0:
                    logger.warning(f"فیلم {title} امتیاز {imdb_score} دارد، رد شد")
                    return None
                imdb = f"{round(imdb_score, 1)}/10"
                genres = []
                for genre in details_data.get('genres', []):
                    genre_name = genre['name']
                    genres.append(GENRE_TRANSLATIONS.get(genre_name, genre_name))
            
            # دریافت تریلر
            trailer = None
            if movie_id:
                for lang in ['', '&language=en-US']:
                    videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}{lang}"
                    async with session.get(videos_url) as videos_response:
                        videos_data = await videos_response.json()
                        if videos_data.get('results'):
                            for video in videos_data['results']:
                                if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                    trailer = f"https://www.youtube.com/watch?v={video['key']}"
                                    break
                            if trailer:
                                break
            
            # انتخاب خلاصه داستان
            plot = shorten_plot(tmdb_plot) if tmdb_plot and is_farsi(tmdb_plot) else None
            if not plot or not is_valid_plot(plot):
                logger.info(f"خلاصه فارسی نامعتبر برای {title}: {plot}")
                plot = shorten_plot(tmdb_plot) if tmdb_plot and is_farsi(tmdb_plot) else "داستان فیلم درباره‌ی یک ماجراجویی هیجان‌انگیز است که شما را شگفت‌زده می‌کند."
                logger.info(f"خلاصه {'فارسی' if is_farsi(plot) else 'فال‌بک'} برای {title}")
            else:
                logger.info(f"خلاصه فارسی از TMDB برای {title}")
            
            previous_plots.append(plot)
            if len(previous_plots) > 10:
                previous_plots.pop(0)
            
            return {
                'title': tmdb_title,
                'year': tmdb_year,
                'plot': plot,
                'imdb': imdb,
                'trailer': trailer,
                'poster': tmdb_poster,
                'genres': genres[:3]
            }
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات فیلم {title}: {str(e)}")
        return None

async def generate_comment(_):
    """تولید تحلیل با Gemini API"""
    logger.info("تولید تحلیل با Gemini")
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = "یک تحلیل کوتاه و جذاب به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، در 3 جمله کامل (هر جمله با نقطه پایان یابد). لحن حرفه‌ای و سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد."
            response = await model.generate_content_async(prompt)
            text = response.text.strip()
            sentences = [s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟']
            if (len(sentences) >= 3 and is_farsi(text) and
                text not in previous_comments and len(text.split()) > 15):
                previous_comments.append(text)
                if len(previous_comments) > 10:
                    previous_comments.pop(0)
                return '. '.join(sentences[:3]) + '.'
            logger.warning(f"تحلیل Gemini نامعتبر (تلاش {attempt + 1}): {text}")
        except Exception as e:
            logger.error(f"خطا در Gemini API (تلاش {attempt + 1}): {str(e)}")
        if attempt == max_attempts - 1:
            logger.warning("تلاش‌های Gemini تمام شد، استفاده از فال‌بک")
            return "این فیلم اثری جذاب است که با داستانی گیرا و جلوه‌های بصری خیره‌کننده، شما را سرگرم می‌کند. بازیگری قوی و کارگردانی حرفه‌ای از نقاط قوت آن است. اگر به دنبال یک تجربه سینمایی مهیج هستید، حتماً تماشا کنید!"

async def fetch_movies_to_cache():
    """آپدیت کش فیلم‌ها از TMDB (100 فیلم)"""
    global cached_movies, last_fetch_time
    logger.info("شروع آپدیت کش فیلم‌ها...")
    try:
        async with aiohttp.ClientSession() as session:
            new_movies = []
            page = 1
            while len(new_movies) < 100 and page <= 5:
                url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page={page}"
                async with session.get(url) as response:
                    data = await response.json()
                    if 'results' not in data or not data['results']:
                        break
                    for m in data['results']:
                        if (m.get('title') and m.get('id') and
                            m.get('original_language') != 'hi' and
                            'IN' not in m.get('origin_country', []) and
                            m.get('vote_average', 0) >= 5.0 and
                            m.get('poster_path')):
                            new_movies.append({'title': m['title'], 'id': m['id']})
                    page += 1
            if new_movies:
                cached_movies = new_movies[:100]
                last_fetch_time = datetime.now()
                logger.info(f"لیست فیلم‌ها آپدیت شد. تعداد: {len(cached_movies)}")
                return True
            logger.error("داده‌ای از TMDB دریافت نشد")
            cached_movies = [
                {'title': 'Inception', 'id': 27205},
                {'title': 'The Matrix', 'id': 603}
            ]
            last_fetch_time = datetime.now()
            return False
    except Exception as e:
        logger.error(f"خطا در آپدیت کش: {str(e)}")
        cached_movies = [
            {'title': 'Inception', 'id': 27205},
            {'title': 'The Matrix', 'id': 603}
        ]
        last_fetch_time = datetime.now()
        return False

async def auto_fetch_movies(context: ContextTypes.DEFAULT_TYPE):
    """آپدیت خودکار کش فیلم‌ها هر 24 ساعت"""
    logger.info("شروع آپدیت خودکار کش...")
    if await fetch_movies_to_cache():
        logger.info("آپدیت خودکار کش موفق بود")
    else:
        logger.error("خطا در آپدیت خودکار کش")
        await context.bot.send_message(ADMIN_ID, "❌ خطا در آپدیت خودکار کش")

async def get_random_movie(max_retries=3):
    """انتخاب فیلم تصادفی با فیلترها"""
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
            comment = await generate_comment(movie_info['title'])
            imdb_score = float(movie_info['imdb'].split('/')[0])
            
            if imdb_score >= 9.0:
                rating = 5
            elif 8.0 <= imdb_score < 9.0:
                rating = 4
            elif 6.5 <= imdb_score < 8.0:
                rating = 3
            elif 5.0 <= imdb_score < 6.5:
                rating = 2
            else:
                rating = 1
            
            return {
                **movie_info,
                'comment': comment,
                'rating': rating,
                'special': imdb_score >= 9.5
            }
        except Exception as e:
            logger.error(f"خطا در انتخاب فیلم (تلاش {attempt + 1}): {str(e)}")
            if attempt == max_retries - 1:
                logger.error("تلاش‌ها تمام شد، استفاده از فال‌بک")
                return FALLBACK_MOVIE
            continue
    logger.error("تلاش‌ها تمام شد، استفاده از فال‌بک")
    return FALLBACK_MOVIE

def format_movie_post(movie):
    """فرمت پست با تگ HTML مثل دیپ‌سیک"""
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie['special'] else ''
    channel_link = 'https://t.me/bestwatch_channel'
    rlm = '\u200F'
    genres = ' '.join([f'#{g.replace(" ", "_")}' for g in movie['genres']]) if movie['genres'] else '#سینمایی'
    
    trailer_section = f"""
🎞 <b>لینک تریلر:</b>
{clean_text(movie['trailer'])}""" if movie['trailer'] and movie['trailer'].startswith('http') else ''
    
    return f"""
🎬 <b>عنوان فیلم:</b>
<b>{clean_text(movie['title'])}{special}</b>

📅 <b>سال تولید: {clean_text(movie['year'])}</b>

📝 <b>خلاصه داستان:</b>
{rlm}{clean_text(movie['plot'])}

🌟 <b>امتیاز:</b>
<b>IMDB: {clean_text(movie['imdb'])}</b>
{trailer_section}

🍿 <b>حرف ما:</b>
{rlm}{clean_text(movie['comment'])}

🎯 <b>ارزش دیدن: {stars}</b>

{genres}

{channel_link}
"""

def get_main_menu():
    """ساخت منوی اصلی با دکمه‌های افقی"""
    keyboard = [
        [
            InlineKeyboardButton("آپدیت لیست", callback_data='fetch_movies'),
            InlineKeyboardButton("ارسال فوری", callback_data='post_now')
        ],
        [
            InlineKeyboardButton("تست‌ها", callback_data='tests_menu'),
            InlineKeyboardButton("اضافه فیلم", callback_data='add_movie')
        ],
        [
            InlineKeyboardButton("آمار بازدید", callback_data='stats')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_tests_menu():
    """ساخت منوی تست‌ها با دکمه‌های افقی"""
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
    """دستور شروع برای ادمین"""
    if str(update.message.from_user.id) != ADMIN_ID:
        logger.info(f"دسترسی غیرمجاز توسط کاربر: {update.message.from_user.id}")
        return
    logger.info("دستور /start اجرا شد")
    await update.message.reply_text("🤖 منوی ادمین:", reply_markup=get_main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش دکمه‌ها"""
    query = update.callback_query
    await query.answer()
    logger.info(f"دکمه زده شد: {query.data}")
    
    try:
        if query.data == 'back_to_main':
            logger.info("بازگشت به منوی اصلی")
            await query.message.edit_text("🤖 منوی ادمین:", reply_markup=get_main_menu())
        elif query.data == 'tests_menu':
            logger.info("نمایش منوی تست‌ها")
            await query.message.edit_text("🛠 منوی تست‌ها:", reply_markup=get_tests_menu())
        elif query.data == 'fetch_movies':
            logger.info("اجرای fetch_movies")
            await fetch_movies(query, context)
        elif query.data == 'post_now':
            logger.info("اجرای post_now")
            await post_now(query, context)
        elif query.data == 'test_all':
            logger.info("اجرای test_all")
            await test_all(query, context)
        elif query.data == 'test_channel':
            logger.info("اجرای test_channel")
            await test_channel(query, context)
        elif query.data == 'stats':
            logger.info("اجرای get_channel_stats")
            await get_channel_stats(query, context)
        elif query.data == 'show_movies':
            logger.info("اجرای show_movies")
            await show_movies(query, context)
        elif query.data == 'add_movie':
            logger.info("شروع add_movie")
            return await add_movie_start(query, context)
        else:
            logger.warning(f"دکمه ناشناخته: {query.data}")
            await query.message.edit_text("❌ دکمه ناشناخته", reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"خطا در پردازش دکمه {query.data}: {str(e)}")
        await query.message.edit_text(f"❌ خطا: {str(e)}", reply_markup=get_main_menu())

async def reset_webhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ریست Webhook تلگرام"""
    if str(update.message.from_user.id) != ADMIN_ID:
        logger.info(f"دسترسی غیرمجاز برای reset_webhook: {update.message.from_user.id}")
        return
    logger.info("اجرای reset_webhook")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
                json={"drop_pending_updates": True}
            ) as response:
                result = await response.json()
                if result.get('ok'):
                    await update.message.reply_text("✅ Webhook ریست شد", reply_markup=get_main_menu())
                else:
                    await update.message.reply_text(f"❌ خطا در ریست Webhook: {result.get('description')}", reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"خطا در ریست Webhook: {e}")
        await update.message.reply_text(f"❌ خطا در ریست Webhook: {str(e)}", reply_markup=get_main_menu())

async def test_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تست دسترسی به کانال"""
    query = update.callback_query
    logger.info("شروع test_channel")
    msg = await query.message.edit_text("در حال تست دسترسی به کانال...")
    try:
        await context.bot.send_message(CHANNEL_ID, "تست دسترسی بات", disable_notification=True)
        await msg.edit_text("✅ دسترسی به کانال اوکی", reply_markup=get_tests_menu())
    except Exception as e:
        logger.error(f"خطا در تست دسترسی به کانال: {str(e)}")
        await msg.edit_text(f"❌ خطا در تست دسترسی به کانال: {str(e)}", reply_markup=get_tests_menu())

async def test_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تست سرویس‌های TMDB، JobQueue و Gemini"""
    query = update.callback_query
    logger.info("شروع test_all")
    msg = await query.message.edit_text("در حال تست سرویس‌ها...")
    results = []
    
    # تست TMDB
    try:
        async with aiohttp.ClientSession() as session:
            tmdb_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=fa-IR&page=1"
            async with session.get(tmdb_url) as tmdb_res:
                tmdb_data = await tmdb_res.json()
                tmdb_status = "✅ TMDB اوکی" if tmdb_data.get('results') else f"❌ TMDB خطا: {tmdb_data}"
        results.append(tmdb_status)
    except Exception as e:
        results.append(f"❌ TMDB خطا: {str(e)}")
    
    # تست JobQueue
    job_queue = context.job_queue
    results.append("✅ JobQueue فعال" if job_queue else "❌ JobQueue غیرفعال")
    
    # تست Gemini
    try:
        comment = await generate_comment(None)
        results.append("✅ Gemini اوکی" if comment else "❌ Gemini خطا")
    except Exception as e:
        results.append(f"❌ Gemini خطا: {str(e)}")
    
    await msg.edit_text("\n".join(results), reply_markup=get_tests_menu())

async def add_movie_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع اضافه کردن فیلم"""
    query = update.callback_query
    logger.info("شروع add_movie_start")
    await query.answer()
    await query.message.edit_text("لطفاً نام فیلم را وارد کنید:")
    return ADD_MOVIE_TITLE

async def add_movie_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش نام فیلم"""
    title = update.message.text.strip()
    logger.info(f"ورودی add_movie_title: {title}")
    if not title:
        await update.message.reply_text("❌ نام فیلم نمی‌تواند خالی باشد", reply_markup=get_main_menu())
        return ConversationHandler.END
    
    msg = await update.message.reply_text(f"در حال اضافه کردن فیلم {title}...")
    logger.info(f"تلاش برای اضافه کردن فیلم: {title}")
    
    try:
        async with aiohttp.ClientSession() as session:
            encoded_title = urllib.parse.quote(title)
            search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=fa-IR"
            async with session.get(search_url) as response:
                data = await response.json()
                logger.info(f"پاسخ TMDB برای {title}: {data}")
                if 'results' not in data or not data['results']:
                    await msg.edit_text(f"❌ فیلم {title} یافت نشد", reply_markup=get_main_menu())
                    return ConversationHandler.END
                
                movie = data['results'][0]
                if (movie.get('original_language') == 'hi' or
                    'IN' in movie.get('origin_country', []) or
                    movie.get('vote_average', 0) < 5.0):
                    await msg.edit_text(f"❌ فیلم {title} شرایط (غیر هندی، امتیاز >= 5) را ندارد", reply_markup=get_main_menu())
                    return ConversationHandler.END
                
                movie_id = movie['id']
                if movie_id in [m['id'] for m in cached_movies]:
                    await msg.edit_text(f"❌ فیلم {title} در لیست موجود است", reply_markup=get_main_menu())
                    return ConversationHandler.END
                
                cached_movies.append({'title': movie['title'], 'id': movie_id})
                await msg.edit_text(f"✅ فیلم {title} به لیست اضافه شد", reply_markup=get_main_menu())
                return ConversationHandler.END
    except Exception as e:
        logger.error(f"خطا در اضافه کردن فیلم {title}: {str(e)}")
        await msg.edit_text(f"❌ خطا در اضافه کردن فیلم: {str(e)}", reply_markup=get_main_menu())
        return ConversationHandler.END

async def add_movie_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو اضافه کردن فیلم"""
    logger.info("لغو add_movie")
    await update.message.reply_text("❌ عملیات لغو شد", reply_markup=get_main_menu())
    return ConversationHandler.END

async def get_channel_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی بازدید کانال بدون پیام تستی"""
    query = update.callback_query
    logger.info("شروع get_channel_stats")
    msg = await query.message.edit_text("در حال بررسی بازدید کانال...")
    
    try:
        now = datetime.now()
        views_24h = []
        views_week = []
        views_month = []
        
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset=-100"
            async with session.get(url) as response:
                data = await response.json()
                logger.info(f"پاسخ getUpdates: {data}")
                if not data.get('ok') or not data.get('result'):
                    raise Exception("هیچ پیامی دریافت نشد. مطمئن شوید بات ادمین کانال است با دسترسی کامل (can_post_messages) و کانال حداقل یک پست اخیر دارد.")
                
                for update in data['result']:
                    if 'channel_post' in update:
                        post = update['channel_post']
                        if post.get('chat', {}).get('id') != int(CHANNEL_ID.replace('@', '')):
                            continue
                        if not post.get('views'):
                            continue
                        message_time = datetime.fromtimestamp(post['date'])
                        time_diff = now - message_time
                        if time_diff <= timedelta(hours=24):
                            views_24h.append(post['views'])
                        if time_diff <= timedelta(days=7):
                            views_week.append(post['views'])
                        if time_diff <= timedelta(days=30):
                            views_month.append(post['views'])
        
        if not views_24h and not views_week and not views_month:
            raise Exception("هیچ بازدیدی ثبت نشد. لطفاً حداقل یک پست در کانال منتشر کنید.")
        
        avg_24h = sum(views_24h) / len(views_24h) if views_24h else 0
        avg_week = sum(views_week) / len(views_week) if views_week else 0
        avg_month = sum(views_month) / len(views_month) if views_month else 0
        
        result = f"""
📊 آمار بازدید کانال:
- میانگین بازدید 24 ساعت گذشته: {avg_24h:.1f}
- میانگین بازدید هفته گذشته: {avg_week:.1f}
- میانگین بازدید ماه گذشته: {avg_month:.1f}
"""
        await msg.edit_text(result, reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"خطا در بررسی بازدید: {str(e)}")
        await msg.edit_text(f"❌ خطا در بررسی بازدید: {str(e)}", reply_markup=get_main_menu())

async def fetch_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آپدیت دستی کش فیلم‌ها"""
    query = update.callback_query
    logger.info("شروع fetch_movies")
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
        logger.error(f"خطا در آپدیت لیست: {str(e)}")
        await msg.edit_text(f"❌ خطا: {str(e)}", reply_markup=get_main_menu())

async def show_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست فیلم‌های کش‌شده"""
    query = update.callback_query
    logger.info("شروع show_movies")
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
        logger.error(f"خطا در نمایش لیست فیلم‌ها: {str(e)}")
        await query.message.edit_text(f"❌ خطا: {str(e)}", reply_markup=get_main_menu())

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال پست دستی"""
    query = update.callback_query
    logger.info("شروع post_now")
    msg = await query.message.edit_text("در حال آماده‌سازی پست...")
    try:
        movie = await get_random_movie()
        if movie:
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
        else:
            await msg.edit_text("❌ خطا در یافتن فیلم", reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"خطا در ارسال پست: {e}")
        await msg.edit_text(f"❌ خطا در ارسال پست: {str(e)}", reply_markup=get_main_menu())

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    """ارسال پست خودکار"""
    logger.info("شروع پست خودکار...")
    try:
        movie = await get_random_movie()
        if movie:
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
        else:
            logger.error("فیلم برای پست خودکار یافت نشد")
            await context.bot.send_message(ADMIN_ID, "❌ خطا: فیلم برای پست خودکار یافت نشد")
    except Exception as e:
        logger.error(f"خطا در ارسال پست خودکار: {e}")
        await context.bot.send_message(ADMIN_ID, f"❌ خطای پست خودکار: {str(e)}")

async def health_check(request):
    """چک سلامت سرور"""
    return web.Response(text="OK")

async def run_bot():
    """راه‌اندازی بات تلگرام"""
    logger.info("شروع راه‌اندازی بات تلگرام...")
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("Application ساخته شد")
    except Exception as e:
        logger.error(f"خطا در ساخت Application: {str(e)}")
        raise
    
    # اضافه کردن هندلرها
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resetwebhook", reset_webhook))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # ConversationHandler برای add_movie
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_movie_start, pattern='^add_movie$')],
        states={
            ADD_MOVIE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie_title)]
        },
        fallbacks=[CommandHandler('cancel', add_movie_cancel)]
    )
    app.add_handler(conv_handler)
    
    job_queue = app.job_queue
    if job_queue:
        logger.info("JobQueue فعال شد")
        # زمان‌بندی موقت: هر 10 دقیقه برای تست
        # TODO: بعداً به 7200 (2 ساعت) برگردانید
        job_queue.run_repeating(auto_post, interval=600, first=10)
        job_queue.run_repeating(auto_fetch_movies, interval=86400, first=60)
    else:
        logger.error("JobQueue فعال نشد، استفاده از زمان‌بندی جایگزین")
        await app.bot.send_message(ADMIN_ID, "⚠️ هشدار: JobQueue فعال نشد، استفاده از زمان‌بندی جایگزین")
        asyncio.create_task(fallback_scheduler(app.context))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    return app

async def fallback_scheduler(context: ContextTypes.DEFAULT_TYPE):
    """زمان‌بندی جایگزین برای پست و آپدیت کش"""
    logger.info("اجرای زمان‌بندی جایگزین...")
    while True:
        await auto_post(context)
        await asyncio.sleep(600)  # هر 10 دقیقه برای تست
        if (datetime.now() - last_fetch_time).seconds > 86400:
            await auto_fetch_movies(context)

async def run_web():
    """راه‌اندازی سرور وب برای Render"""
    logger.info("شروع راه‌اندازی سرور وب...")
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"سرور وب روی پورت {PORT} فعال شد")
    return runner

async def main():
    """راه‌اندازی بات و سرور وب"""
    logger.info("شروع برنامه...")
    if not await fetch_movies_to_cache():
        logger.error("خطا در دریافت اولیه لیست فیلم‌ها")
    
    # ریست Webhook در شروع
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
    
    # راه‌اندازی بات و سرور وب
    bot_app = await run_bot()
    web_runner = await run_web()
    
    # نگه‌داشتن برنامه در حال اجرا
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
