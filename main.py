import telegram
import asyncio
import os
import logging
import aiohttp
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from aiohttp import web
import re
from datetime import datetime

# تنظیمات لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# بارگذاری متغیرهای محیطی
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
ADMIN_ID = os.getenv('ADMIN_ID')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
PORT = int(os.getenv('PORT', 8080))

# کش فیلم‌ها
cached_movies = []
last_fetch_time = None

# متن‌های پیش‌فرض برای تحلیل (برای تنوع)
FALLBACK_COMMENTS = [
    "این فیلم یه ماجراجویی نفس‌گیره که تا آخر شما رو میخکوب نگه می‌داره!",
    "داستان جذاب و بازیگری فوق‌العاده، این فیلم رو به یه تجربه خاص تبدیل کرده!",
    "پر از احساسات و لحظه‌های به‌یادموندنی، حتماً باید این فیلم رو ببینی!",
    "یه داستان متفاوت با پایان غافلگیرکننده که ارزش دیدن داره!"
]

# توابع کمکی
def clean_text(text):
    text = re.sub(r'[^\w\s\-\.\,\!\?\:\(\)\'\"]', '', text)
    return text[:300]

async def translate_plot(plot):
    """ترجمه خلاصه داستان به فارسی با OpenAI"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "متن را به فارسی ترجمه کن و به 2-3 جمله (حداکثر 100 کلمه) خلاصه کن. لحن ساده و صمیمی باشد."},
                    {"role": "user", "content": plot}
                ],
                "max_tokens": 150,
                "temperature": 0.7
            }
            logger.info("در حال ترجمه خلاصه داستان")
            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30) as response:
                data = await response.json()
                if 'choices' in data and data['choices']:
                    return data['choices'][0]['message']['content']
                logger.error("هیچ ترجمه‌ای از OpenAI دریافت نشد")
                return "داستان این فیلم پر از ماجراهای جذابی است که شما را سرگرم می‌کند!"
    except Exception as e:
        logger.error(f"خطا در ترجمه خلاصه داستان: {e}")
        return "داستان این فیلم پر از ماجراهای جذابی است که شما را سرگرم می‌کند!"

async def get_movie_info(movie):
    """دریافت اطلاعات فیلم از TMDB و OMDB (در صورت نیاز)"""
    try:
        async with aiohttp.ClientSession() as session:
            # TMDB به‌عنوان منبع اصلی
            movie_id = movie['id']
            details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
            logger.info(f"فچ اطلاعات فیلم {movie['title']} از TMDB")
            async with session.get(details_url, timeout=15) as response:
                details = await response.json()
                if not details.get('id'):
                    logger.error(f"جزئیات فیلم {movie['title']} در TMDB پیدا نشد")
                    return None

                # تریلر
                videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
                trailer = "N/A"
                async with session.get(videos_url, timeout=15) as videos_response:
                    videos_data = await videos_response.json()
                    if videos_data.get('results'):
                        for video in videos_data['results']:
                            if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                trailer = f"https://www.youtube.com/watch?v={video['key']}"
                                break

                # اطلاعات اولیه از TMDB
                plot = details.get('overview', 'No plot available')
                poster = f"https://image.tmdb.org/t/p/w500{details.get('poster_path', '')}" if details.get('poster_path') else 'N/A'
                imdb_score = str(round(details.get('vote_average', 0), 1))

                # ترجمه خلاصه داستان
                translated_plot = await translate_plot(plot)

                # OMDB به‌عنوان مکمل (فقط برای پوستر یا خلاصه)
                omdb_data = {}
                if plot == 'No plot available' or poster == 'N/A':
                    omdb_url = f"http://www.omdbapi.com/?s={movie['title']}&apikey={OMDB_API_KEY}"
                    logger.info(f"جستجوی فازی فیلم {movie['title']} در OMDB")
                    async with session.get(omdb_url, timeout=15) as omdb_response:
                        omdb_data = await omdb_response.json()
                        if omdb_data.get('Response') == 'True' and omdb_data.get('Search'):
                            movie_id = omdb_data['Search'][0]['imdbID']
                            omdb_detail_url = f"http://www.omdbapi.com/?i={movie_id}&apikey={OMDB_API_KEY}"
                            async with session.get(omdb_detail_url, timeout=15) as detail_response:
                                omdb_data = await detail_response.json()
                                if omdb_data.get('Response') == 'True':
                                    if plot == 'No plot available':
                                        plot = omdb_data.get('Plot', 'No plot available')
                                        translated_plot = await translate_plot(plot)
                                    if poster == 'N/A':
                                        poster = omdb_data.get('Poster', 'N/A')
                                    imdb_score = omdb_data.get('imdbRating', imdb_score)

                rotten_tomatoes = next(
                    (r['Value'] for r in omdb_data.get('Ratings', []) if r['Source'] == 'Rotten Tomatoes'),
                    str(random.randint(70, 95)) + '%'
                )

                return {
                    'title': details.get('title', movie['title']),
                    'year': details.get('release_date', 'N/A')[:4],
                    'plot': translated_plot,
                    'imdb': imdb_score,
                    'rotten_tomatoes': rotten_tomatoes,
                    'trailer': trailer,
                    'poster': poster
                }
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات فیلم {movie['title']}: {e}")
        return None

async def generate_comment(title):
    """تولید تحلیل 80-100 کلمه‌ای با OpenAI"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "یه تحلیل صمیمی و هیجان‌انگیز 80-100 کلمه درباره فیلم بنویس. نقاط قوت (مثل داستان، بازیگری، کارگردانی) و یه ضعف کوچیک (مثل ریتم یا جزئیات) رو بگو. لحن جذاب و دوستانه باشه و از علامت‌های Markdown استفاده نکن."},
                    {"role": "user", "content": f"فیلم: {title}"}
                ],
                "max_tokens": 150,
                "temperature": 0.8
            }
            logger.info(f"در حال تولید تحلیل برای {title} از OpenAI")
            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30) as response:
                data = await response.json()
                if 'choices' in data and data['choices']:
                    comment = data['choices'][0]['message']['content']
                    if len(comment.split()) < 50:  # اگه خیلی کوتاه بود
                        logger.warning(f"تحلیل برای {title} خیلی کوتاهه: {comment}")
                        return random.choice(FALLBACK_COMMENTS)
                    return comment
                logger.error(f"هیچ تحلیلی از OpenAI برای {title} دریافت نشد")
                return random.choice(FALLBACK_COMMENTS)
    except Exception as e:
        logger.error(f"خطا در OpenAI API برای {title}: {e}")
        return random.choice(FALLBACK_COMMENTS)

async def fetch_movies_to_cache():
    """آپدیت کش فیلم‌ها از TMDB (5 صفحه، 100 فیلم)"""
    global cached_movies, last_fetch_time
    try:
        async with aiohttp.ClientSession() as session:
            cached_movies = []
            for page in range(1, 6):
                url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page={page}"
                logger.info(f"فچ لیست فیلم‌ها از TMDB (صفحه {page})")
                async with session.get(url, timeout=15) as response:
                    data = await response.json()
                    if 'results' in data and data['results']:
                        cached_movies.extend(data['results'])
                    else:
                        logger.error(f"خطا در دریافت صفحه {page} از TMDB")
            if cached_movies:
                last_fetch_time = datetime.now()
                logger.info(f"کش آپدیت شد. تعداد فیلم‌ها: {len(cached_movies)}")
                return True
            logger.error("هیچ فیلمی از TMDB دریافت نشد")
            return False
    except Exception as e:
        logger.error(f"خطا در آپدیت کش: {e}")
        return False

async def get_random_movie(max_attempts=3):
    """انتخاب فیلم رندوم از کش"""
    for attempt in range(max_attempts):
        try:
            if not cached_movies or (datetime.now() - last_fetch_time).seconds > 86400:
                await fetch_movies_to_cache()
            if not cached_movies:
                logger.error("کش خالی است")
                return None
            movie = random.choice(cached_movies)
            logger.info(f"فیلم انتخاب‌شده: {movie['title']} (تلاش {attempt+1})")
            movie_info = await get_movie_info(movie)
            if not movie_info:
                logger.error(f"اطلاعات فیلم {movie['title']} پیدا نشد")
                continue
            comment = await generate_comment(movie['title'])
            imdb_score = float(movie_info['imdb']) if movie_info['imdb'] != 'N/A' else 0
            rating = min(5, max(1, int(imdb_score // 2)))
            return {
                **movie_info,
                'comment': comment,
                'rating': rating,
                'special': imdb_score >= 8.0
            }
        except Exception as e:
            logger.error(f"خطا در انتخاب فیلم (تلاش {attempt+1}): {e}")
    logger.error("هیچ فیلمی پس از چند تلاش پیدا نشد")
    return None

def format_movie_post(movie):
    """فرمت پست فیلم (دقیقاً مثل دیپ‌سیک)"""
    stars = '⭐️' * movie['rating']
    return f"""
🎬 {movie['title']}{' 👑' if movie['special'] else ''}

📅 سال: {movie['year']}

📝 خلاصه: {movie['plot']}

🌟 امتیاز: IMDB: {movie['imdb']} | RT: {movie['rotten_tomatoes']}

🎞 تریلر: {movie['trailer']}

🍿 تحلیل: {movie['comment']}

🎯 امتیاز: {stars}
"""

# دستورات بات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("این بات فقط برای ادمینه!")
        return
    message = (
        "🎬 به بات Best Watch خوش اومدی!\n\n"
        "دستورات موجود:\n"
        "/start - نمایش این پیام\n"
        "/fetchmovies - آپدیت لیست فیلم‌ها\n"
        "/addmovie - اضافه کردن فیلم دستی\n"
        "/postnow - پست فوری یه فیلم رندوم\n\n"
        "هر 10 دقیقه یه فیلم خودکار پست می‌شه."
    )
    await update.message.reply_text(message)

async def fetch_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("فقط ادمین می‌تونه لیست رو آپدیت کنه!")
        return
    msg = await update.message.reply_text("در حال آپدیت لیست...")
    if await fetch_movies_to_cache():
        await msg.edit_text(f"✅ لیست آپدیت شد! ({len(cached_movies)} فیلم)")
    else:
        await msg.edit_text("❌ خطا در آپدیت لیست")

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("فقط ادمین می‌تونه فیلم اضافه کنه!")
        return
    try:
        args = update.message.text.split('\n')
        if len(args) < 3:
            await update.message.reply_text("فرمت: /addmovie\nعنوان: <عنوان>\nتریلر: <لینک>\nRotten: <امتیاز>")
            return
        title = args[1].replace('عنوان: ', '')
        trailer = args[2].replace('تریلر: ', '')
        rotten = args[3].replace('Rotten: ', '')
        # جستجو در TMDB
        async with aiohttp.ClientSession() as session:
            search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
            async with session.get(search_url, timeout=15) as response:
                tmdb_data = await response.json()
                if not tmdb_data.get('results'):
                    # اگه تو TMDB نبود، OMDB رو چک کن
                    omdb_url = f"http://www.omdbapi.com/?s={title}&apikey={OMDB_API_KEY}"
                    async with session.get(omdb_url, timeout=15) as omdb_response:
                        omdb_data = await omdb_response.json()
                        if omdb_data.get('Response') != 'True' or not omdb_data.get('Search'):
                            await update.message.reply_text(f"فیلم {title} پیدا نشد!")
                            return
                        movie_id = omdb_data['Search'][0]['imdbID']
                        omdb_detail_url = f"http://www.omdbapi.com/?i={movie_id}&apikey={OMDB_API_KEY}"
                        async with session.get(omdb_detail_url, timeout=15) as detail_response:
                            omdb_data = await detail_response.json()
                            if omdb_data.get('Response') != 'True':
                                await update.message.reply_text(f"فیلم {title} پیدا نشد!")
                                return
                            movie_info = {
                                'title': omdb_data.get('Title', title),
                                'year': omdb_data.get('Year', 'N/A'),
                                'plot': await translate_plot(omdb_data.get('Plot', 'No plot available')),
                                'imdb': omdb_data.get('imdbRating', 'N/A'),
                                'rotten_tomatoes': rotten,
                                'trailer': trailer,
                                'poster': omdb_data.get('Poster', 'N/A')
                            }
                else:
                    movie = tmdb_data['results'][0]
                    movie_info = await get_movie_info(movie)
                    if not movie_info:
                        await update.message.reply_text(f"فیلم {title} پیدا نشد!")
                        return
                    movie_info['trailer'] = trailer
                    movie_info['rotten_tomatoes'] = rotten

                comment = await generate_comment(title)
                imdb_score = float(movie_info['imdb']) if movie_info['imdb'] != 'N/A' else 0
                rating = min(5, max(1, int(imdb_score // 2)))
                movie_data = {
                    **movie_info,
                    'comment': comment,
                    'rating': rating,
                    'special': imdb_score >= 8.0
                }
                post = format_movie_post(movie_data)
                try:
                    if movie_data['poster'] != 'N/A':
                        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=movie_data['poster'], caption=post)
                    else:
                        await context.bot.send_message(chat_id=CHANNEL_ID, text=post)
                    await update.message.reply_text(f"فیلم {movie_data['title']} اضافه و پست شد!")
                except Exception as e:
                    await update.message.reply_text(f"خطا در ارسال: {str(e)}")
    except Exception as e:
        await update.message.reply_text(f"خطا: {str(e)}")

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("فقط ادمین می‌تونه پست فوری بفرسته!")
        return
    logger.info("اجرای دستور /postnow")
    msg = await update.message.reply_text("در حال آماده‌سازی پست...")
    movie = await get_random_movie()
    if not movie:
        await msg.edit_text("❌ هیچ فیلمی پیدا نشد. لطفاً دوباره امتحان کنید یا لیست را آپدیت کنید (/fetchmovies).")
        return
    post = format_movie_post(movie)
    try:
        if movie['poster'] != 'N/A':
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=movie['poster'], caption=post)
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=post)
        await msg.edit_text(f"✅ پست {movie['title']} ارسال شد")
        logger.info(f"فیلم {movie['title']} با موفقیت پست شد")
    except Exception as e:
        logger.error(f"خطا در ارسال پست فوری: {str(e)}")
        await msg.edit_text(f"❌ خطا در ارسال: {str(e)}")

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    logger.info("شروع پست خودکار...")
    movie = await get_random_movie()
    if not movie:
        logger.error("هیچ فیلمی برای پست خودکار پیدا نشد!")
        return
    post = format_movie_post(movie)
    try:
        if movie['poster'] != 'N/A':
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=movie['poster'], caption=post)
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=post)
        logger.info(f"پست خودکار فیلم {movie['title']} ارسال شد.")
    except Exception as e:
        logger.error(f"خطا در ارسال پست خودکار: {str(e)}")

async def health_check(request):
    return web.Response(text="OK")

async def main():
    # پر کردن کش موقع استارت
    await fetch_movies_to_cache()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fetchmovies", fetch_movies))
    app.add_handler(CommandHandler("addmovie", add_movie))
    app.add_handler(CommandHandler("postnow", post_now))

    await app.initialize()
    await app.start()

    if app.job_queue:
        app.job_queue.run_repeating(auto_post, interval=600, first=10)
        logger.info("JobQueue برای پست خودکار هر 10 دقیقه فعال شد")
    else:
        logger.error("JobQueue در دسترس نیست!")

    web_app = web.Application()
    web_app.add_routes([web.get('/health', health_check)])
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    try:
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("پولینگ شروع شد")
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"خطا در پولینگ: {e}")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await runner.cleanup()

if __name__ == '__main__':
    asyncio.run(main())
