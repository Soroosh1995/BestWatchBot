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
from google.api_core import exceptions as google_exceptions
from openai import AsyncOpenAI

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
PORT = int(os.getenv('PORT', 8080))

# تنظیم Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# تنظیم Open AI
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# --- کش و متغیرهای سراسری ---
cached_movies = []
posted_movies = []
last_fetch_time = None
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

# --- فال‌بک‌های خلاصه داستان و حرف ما ---
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

# --- حالت‌های ConversationHandler ---
ADD_MOVIE_TITLE = 1

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

async def get_movie_info(title):
    logger.info(f"دریافت اطلاعات برای فیلم: {title}")
    try:
        async with aiohttp.ClientSession() as session:
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
            
            details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
            async with session.get(details_url) as details_response:
                details_data = await details_response.json()
                original_language = details_data.get('original_language', 'en')
                imdb_score = details_data.get('vote_average', 0)
                if imdb_score < 6.0:
                    logger.warning(f"فیلم {title} امتیاز {imdb_score} دارد، رد شد")
                    return None
                imdb = f"{imdb_score:.1f}/10"
                genres = []
                for genre in details_data.get('genres', []):
                    genre_name = genre['name']
                    genres.append(GENRE_TRANSLATIONS.get(genre_name, genre_name))
            
            search_url_fa = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=fa-IR"
            async with session.get(search_url_fa) as tmdb_response_fa:
                tmdb_data_fa = await tmdb_response_fa.json()
                tmdb_plot = tmdb_data_fa['results'][0].get('overview', '') if tmdb_data_fa.get('results') else ''
                tmdb_year = tmdb_data_fa['results'][0].get('release_date', 'N/A')[:4] if tmdb_data_fa.get('results') else 'N/A'
            
            trailer = None
            videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}&language={original_language}"
            async with session.get(videos_url) as videos_response:
                videos_data = await videos_response.json()
                if videos_data.get('results'):
                    for video in videos_data['results']:
                        if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                            trailer = f"https://www.youtube.com/watch?v={video['key']}"
                            break
            
            plot = shorten_plot(tmdb_plot) if tmdb_plot and is_farsi(tmdb_plot) else None
            if not plot or not is_valid_plot(plot):
                logger.info(f"خلاصه فارسی نامعتبر برای {title}: {plot}")
                plot = get_fallback_by_genre(FALLBACK_PLOTS, genres)
                logger.info(f"خلاصه فال‌بک برای {title}")
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
    
    if openai_available and not gemini_available:
        try:
            response = await client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a professional film critic writing in Persian."},
                    {"role": "user", "content": "یک تحلیل کوتاه و جذاب به فارسی برای یک فیلم بنویس، بدون ذکر نام فیلم، در 3 جمله کامل (هر جمله با نقطه پایان یابد). لحن حرفه‌ای و سینمایی داشته باشد و متن متنوع و متفاوت از تحلیل‌های قبلی باشد. فقط به فارسی بنویس و از کلمات انگلیسی استفاده نکن."}
                ],
                max_tokens=150,
                temperature=0.7
            )
            text = response.choices[0].message.content.strip()
            sentences = [s.strip() for s in text.split('. ') if s.strip() and s.strip()[-1] in '.!؟']
            if len(sentences) >= 3 and is_farsi(text) and len(text.split()) > 15:
                previous_comments.append(text)
                if len(previous_comments) > 10:
                    previous_comments.pop(0)
                return '. '.join(sentences[:3]) + '.'
            logger.warning(f"تحلیل Open AI نامعتبر: {text}")
        except Exception as e:
            logger.error(f"خطا در Open AI API: {str(e)}")
            openai_available = False
            await send_admin_alert(None, "❌ توکن Open AI تمام شده است. هیچ تحلیلگر دیگری در دسترس نیست.")
    
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
                            m.get('vote_average', 0) >= 6.0 and
                            m.get('poster_path')):
                            new_movies.append({'title': m['title'], 'id': m['id']})
                    page += 1
            if new_movies:
                cached_movies = new_movies[:100]
                last_fetch_time = datetime.now()
                logger.info(f"لیست فیلم‌ها آپدیت شد. تعداد: {len(cached_movies)}")
                return True
            logger.error("داده‌ای از TMDB دریافت نشد")
            cached_movies = [{'title': 'Inception', 'id': 27205}, {'title': 'The Matrix', 'id': 603}]
            last_fetch_time = datetime.now()
            return False
    except Exception as e:
        logger.error(f"خطا در آپدیت کش: {str(e)}")
        cached_movies = [{'title': 'Inception', 'id': 27205}, {'title': 'The Matrix', 'id': 603}]
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
            if imdb_score >= 9.0:
                rating = 5
            elif 8.0 <= imdb_score < 9.0:
                rating = 4
            elif 7.0 <= imdb_score < 8.0:
                rating = 3
            elif 6.0 <= imdb_score < 7.0:
                rating = 2
            else:
                rating = 1
            
            return {
                **movie_info,
                'comment': comment,
                'rating': rating,
                'special': imdb_score >= 9.0
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
🌟 <b>امتیاز:</b>
<b>IMDB: {clean_text(movie['imdb']) or 'نامشخص'}</b>
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
            InlineKeyboardButton("اضافه فیلم", callback_data='add_movie')
        ],
        [
            InlineKeyboardButton("آمار بازدید", callback_data='stats'),
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
    
    try:
        async with aiohttp.ClientSession() as session:
            tmdb_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=fa-IR&page=1"
            async with session.get(tmdb_url) as tmdb_res:
                tmdb_data = await tmdb_res.json()
                tmdb_status = "✅ TMDB اوکی" if tmdb_data.get('results') else f"❌ TMDB خطا: {tmdb_data}"
        results.append(tmdb_status)
    except Exception as e:
        results.append(f"❌ TMDB خطا: {str(e)}")
    
    job_queue = context.job_queue
    results.append("✅ JobQueue فعال" if job_queue else "❌ JobQueue غیرفعال")
    
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
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4",
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
        results.append(f"❌ Open AI خطا: {str(e)}")
    
    await msg.edit_text("\n".join(results), reply_markup=get_tests_menu())

async def test_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه test_channel")
    await query.answer()
    msg = await query.message.edit_text("در حال تست دسترسی به کانال...")
    try:
        await context.bot.send_message(CHANNEL_ID, "تست دسترسی بات", disable_notification=True)
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
                    raise Exception("بات ادمین کانال نیست. لطفاً بات را ادمین کنید.")
        
        now = datetime.now()
        views_24h = []
        views_week = []
        views_month = []
        
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
                        if time_diff <= timedelta(hours=24):
                            views_24h.append(post['views'])
                        if time_diff <= timedelta(days=7):
                            views_week.append(post['views'])
                        if time_diff <= timedelta(days=30):
                            views_month.append(post['views'])
        
        if not views_24h and not views_week and not views_month:
            raise Exception("هیچ پستی در کانال یافت نشد. لطفاً حداقل یک پست منتشر کنید.")
        
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

async def add_movie_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info("دکمه add_movie")
    await query.answer()
    await query.message.edit_text("لطفاً نام فیلم را وارد کنید:")
    return ADD_MOVIE_TITLE

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

async def add_movie_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    logger.info(f"ورودی add_movie_title: {title}")
    if not title:
        await update.message.reply_text("❌ نام فیلم نمی‌تواند خالی باشد", reply_markup=get_main_menu())
        return ConversationHandler.END
    
    msg = await update.message.reply_text(f"در حال جستجوی فیلم {title}...")
    logger.info(f"تلاش برای اضافه کردن فیلم: {title}")
    
    try:
        async with aiohttp.ClientSession() as session:
            encoded_title = urllib.parse.quote(title)
            search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=en-US"
            async with session.get(search_url) as response:
                data = await response.json()
                logger.info(f"پاسخ TMDB برای {title}: {data}")
                if not data.get('results'):
                    await msg.edit_text(f"❌ فیلم {title} یافت نشد", reply_markup=get_main_menu())
                    return ConversationHandler.END
                
                movie = data['results'][0]
                movie_id = movie.get('id')
                vote_average = movie.get('vote_average', 0)
                original_language = movie.get('original_language', '')
                origin_country = movie.get('origin_country', [])
                
                if original_language == 'hi' or 'IN' in origin_country:
                    await msg.edit_text(f"❌ فیلم {title} هندی است و مجاز نیست", reply_markup=get_main_menu())
                    return ConversationHandler.END
                
                if vote_average < 6.0:
                    await msg.edit_text(f"❌ فیلم {title} امتیاز {vote_average:.1f} دارد (حداقل 6.0)", reply_markup=get_main_menu())
                    return ConversationHandler.END
                
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
    logger.info("لغو add_movie")
    await update.message.reply_text("❌ عملیات لغو شد", reply_markup=get_main_menu())
    return ConversationHandler.END

async def reset_webhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    app.add_handler(CommandHandler("resetwebhook", reset_webhook))
    
    app.add_handler(CallbackQueryHandler(back_to_main, pattern='^back_to_main$'))
    app.add_handler(CallbackQueryHandler(tests_menu, pattern='^tests_menu$'))
    app.add_handler(CallbackQueryHandler(fetch_movies_handler, pattern='^fetch_movies$'))
    app.add_handler(CallbackQueryHandler(post_now_handler, pattern='^post_now$'))
    app.add_handler(CallbackQueryHandler(test_all_handler, pattern='^test_all$'))
    app.add_handler(CallbackQueryHandler(test_channel_handler, pattern='^test_channel$'))
    app.add_handler(CallbackQueryHandler(stats_handler, pattern='^stats$'))
    app.add_handler(CallbackQueryHandler(show_movies_handler, pattern='^show_movies$'))
    app.add_handler(CallbackQueryHandler(add_movie_start, pattern='^add_movie$'))
    app.add_handler(CallbackQueryHandler(toggle_bot_handler, pattern='^toggle_bot$'))
    
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
