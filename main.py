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
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
PORT = int(os.getenv('PORT', 8080))

# کش فیلم‌ها
cached_movies = []
last_fetch_time = None

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
                    {"role": "system", "content": "خلاصه داستان را به فارسی ترجمه کن و به 2-3 جمله (حداکثر 100 کلمه) خلاصه کن."},
                    {"role": "user", "content": plot}
                ],
                "max_tokens": 150
            }
            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=15) as response:
                data = await response.json()
                if 'choices' in data and data['choices']:
                    return data['choices'][0]['message']['content']
                return plot
    except Exception as e:
        logger.error(f"خطا در ترجمه خلاصه داستان: {e}")
        return plot

async def get_movie_info(title):
    """دریافت اطلاعات فیلم از OMDB و TMDB"""
    try:
        async with aiohttp.ClientSession() as session:
            # OMDB
            omdb_url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            logger.info(f"فچ اطلاعات فیلم {title} از OMDB")
            async with session.get(omdb_url, timeout=15) as response:
                omdb_data = await response.json()
                if omdb_data.get('Response') != 'True':
                    logger.error(f"فیلم {title} در OMDB پیدا نشد")
                    return None

                # TMDB برای تریلر
                search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
                async with session.get(search_url, timeout=15) as tmdb_response:
                    tmdb_data = await tmdb_response.json()
                    trailer = "N/A"
                    if tmdb_data.get('results'):
                        movie_id = tmdb_data['results'][0]['id']
                        videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
                        async with session.get(videos_url, timeout=15) as videos_response:
                            videos_data = await videos_response.json()
                            if videos_data.get('results'):
                                for video in videos_data['results']:
                                    if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                        trailer = f"https://www.youtube.com/watch?v={video['key']}"
                                        break

                # ترجمه خلاصه داستان
                plot = omdb_data.get('Plot', 'No plot available')
                translated_plot = await translate_plot(plot)

                rotten_tomatoes = next(
                    (r['Value'] for r in omdb_data.get('Ratings', []) if r['Source'] == 'Rotten Tomatoes'),
                    str(random.randint(70, 95)) + '%'
                )
                return {
                    'title': omdb_data.get('Title', title),
                    'year': omdb_data.get('Year', 'N/A'),
                    'plot': translated_plot,
                    'imdb': omdb_data.get('imdbRating', 'N/A'),
                    'rotten_tomatoes': rotten_tomatoes,
                    'trailer': trailer,
                    'poster': omdb_data.get('Poster', 'N/A')
                }
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات فیلم {title}: {e}")
        return None

async def generate_comment(title):
    """تولید تحلیل 80-100 کلمه‌ای با OpenAI"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "یه تحلیل صمیمی و هیجان‌انگیز 80-100 کلمه‌ای درباره فیلم بنویس. نقاط قوت و یه ضعف کوچیک رو بگو. از علامت‌های Markdown استفاده نکن."},
                    {"role": "user", "content": f"فیلم: {title}"}
                ],
                "max_tokens": 150
            }
            logger.info(f"تولید کامنت برای {title} از OpenAI")
            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=15) as response:
                data = await response.json()
                if 'choices' in data and data['choices']:
                    return data['choices'][0]['message']['content']
                logger.error(f"هیچ کامنتی از OpenAI برای {title} دریافت نشد")
                return "این فیلم یه تجربه فوق‌العاده‌ست! حتماً ببینید!"
    except Exception as e:
        logger.error(f"خطا در OpenAI API برای {title}: {e}")
        return "این فیلم یه تجربه فوق‌العاده‌ست! حتماً ببینید!"

async def fetch_movies_to_cache():
    """آپدیت کش فیلم‌ها از TMDB"""
    global cached_movies, last_fetch_time
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page=1"
            logger.info(f"فچ لیست فیلم‌ها از TMDB")
            async with session.get(url, timeout=15) as response:
                data = await response.json()
                if 'results' in data and data['results']:
                    cached_movies = data['results']
                    last_fetch_time = datetime.now()
                    logger.info(f"کش آپدیت شد. تعداد فیلم‌ها: {len(cached_movies)}")
                    return True
                logger.error("خطا در دریافت لیست از TMDB")
                return False
    except Exception as e:
        logger.error(f"خطا در آپدیت کش: {e}")
        return False

async def get_random_movie():
    """انتخاب فیلم رندوم از کش"""
    try:
        if not cached_movies or (datetime.now() - last_fetch_time).seconds > 86400:
            await fetch_movies_to_cache()
        if not cached_movies:
            logger.error("کش خالی است")
            return None
        movie = random.choice(cached_movies)
        movie_info = await get_movie_info(movie['title'])
        if not movie_info:
            logger.error(f"اطلاعات فیلم {movie['title']} پیدا نشد")
            return None
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
        logger.error(f"خطا در انتخاب فیلم: {e}")
        return None

def format_movie_post(movie):
    """فرمت پست فیلم"""
    stars = '⭐️' * movie['rating']
    return f"""
🎬 {movie['title']}{' 👑' if movie['special'] else ''}
📅 سال: {movie['year']}
📝 خلاصه: {movie['plot']}
🌟 امتیاز: IMDB: {movie['imdb']} | RT: {movie['rotten_tomatoes']}
🎞 تریلر: {movie['trailer']}
🍿 حرف ما: {movie['comment']}
🎯 امتیاز: {stars}
https://t.me/bestwatch_channel
"""

# دستورات بات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("این بات فقط برای ادمینه!")
        return
    message = (
        "🎬 به بات Best Watch خوش اومدی!\n\n"
        "این بات برای مدیریت کانال @bestwatch_channelه.\n"
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
        movie_info = await get_movie_info(title)
        if not movie_info:
            await update.message.reply_text(f"فیلم {title} پیدا نشد!")
            return
        movie_info['trailer'] = trailer
        movie_info['rotten_tomatoes'] = rotten
        comment = await generate_comment(title)
        imdb_score = float(movie_info['imdb']) if movie_info['imdb'] != 'N/A' else 0
        rating = min(5, max(1, int(imdb_score // 2)))
        movie = {
            **movie_info,
            'comment': comment,
            'rating': rating,
            'special': imdb_score >= 8.0
        }
        post = format_movie_post(movie)
        try:
            if movie['poster'] != 'N/A':
                await context.bot.send_photo(chat_id=CHANNEL_ID, photo=movie['poster'], caption=post)
            else:
                await context.bot.send_message(chat_id=CHANNEL_ID, text=post)
            await update.message.reply_text(f"فیلم {movie['title']} اضافه و پست شد!")
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
        await msg.edit_text("❌ خطا در یافتن فیلم")
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
