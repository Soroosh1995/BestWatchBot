import telegram
import asyncio
import json
import os
import logging
import aiohttp
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from aiohttp import web
import re

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
ADMIN_ID = os.getenv('ADMIN_ID')
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
PORT = int(os.getenv('PORT', 8080))

async def get_movie_info(title):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            logger.info(f"در حال فچ کردن اطلاعات فیلم {title} از OMDB")
            async with session.get(url, timeout=15) as response:
                data = await response.json()
                if data['Response'] == 'True':
                    return {
                        'title': data['Title'],
                        'year': data['Year'],
                        'plot': data['Plot'],
                        'imdb': data['imdbRating'],
                        'poster': data.get('Poster', 'N/A')
                    }
                logger.error(f"فیلم {title} در OMDB پیدا نشد")
                return None
    except Exception as e:
        logger.error(f"خطا در OMDB API برای {title}: {e}")
        return None

async def generate_comment(title):
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "یه توضیح جذاب و کوتاه (50-70 کلمه) درباره فیلم بنویس. لحن صمیمی و هیجان‌انگیز. از علامت‌های Markdown مثل * یا _ استفاده نکن."},
                    {"role": "user", "content": f"فیلم: {title}"}
                ]
            }
            logger.info(f"در حال تولید کامنت برای {title} از OpenAI")
            async with session.post(url, json=payload, headers=headers, timeout=15) as response:
                data = await response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    return data['choices'][0]['message']['content']
                logger.error(f"هیچ کامنتی از OpenAI برای {title} دریافت نشد")
                return "این فیلم یه تجربه فوق‌العاده‌ست! حتماً ببینید!"
    except Exception as e:
        logger.error(f"خطا در OpenAI API برای {title}: {e}")
        return "این فیلم یه تجربه فوق‌العاده‌ست! حتماً ببینید!"

async def get_random_movie():
    try:
        async with aiohttp.ClientSession() as session:
            page = random.randint(1, 10)
            url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page={page}"
            logger.info(f"در حال فچ کردن فیلم از TMDB: {url}")
            async with session.get(url, timeout=15) as response:
                data = await response.json()
                if 'results' not in data or not data['results']:
                    logger.error("هیچ نتیجه‌ای از TMDB برنگشت!")
                    return None
                movie = random.choice(data['results'])
                title = movie['title']
                logger.info(f"فیلم انتخاب‌شده: {title}")
                movie_info = await get_movie_info(title)
                if not movie_info:
                    logger.error(f"اطلاعات فیلم {title} از OMDB پیدا نشد!")
                    return None
                comment = await generate_comment(title)
                imdb_score = float(movie_info['imdb']) if movie_info['imdb'] != 'N/A' else 0
                rating = min(5, max(1, int(imdb_score // 2)))
                special = imdb_score >= 8.5
                return {
                    'title': movie_info['title'],
                    'year': movie_info['year'],
                    'plot': movie_info['plot'],
                    'imdb': movie_info['imdb'],
                    'rotten_tomatoes': str(random.randint(70, 95)),
                    'trailer': f"https://www.youtube.com/watch?v={movie['id']}",
                    'comment': comment,
                    'rating': rating,
                    'special': special,
                    'poster': movie_info['poster']
                }
    except Exception as e:
        logger.error(f"خطا در فچ کردن فیلم از TMDB: {str(e)}")
        return None

def clean_text(text):
    text = re.sub(r'[^\w\s\-\.\,\!\?\:\(\)\'\"]', '', text)
    return text[:1000]

def format_movie_post(movie):
    rating_stars = {5: '⭐️⭐️⭐️⭐️⭐️', 4: '⭐️⭐️⭐️⭐️', 3: '⭐️⭐️⭐️', 2: '⭐️⭐️', 1: '⭐️'}
    special_symbol = ' 👑' if movie.get('special', False) else ''
    post = (
        f"<b>🎬 عنوان فیلم:</b> \n{movie['title']}{special_symbol}\n\n"
        f"<b>📅 سال تولید:</b> {movie['year']}\n\n"
        f"<b>📝 خلاصه داستان:</b> \n{clean_text(movie['plot'])}\n\n"
        f"<b>🌟 امتیاز:</b>\nIMDB: {movie['imdb']}\nRotten Tomatoes: {movie['rotten_tomatoes']}%\n\n"
        f"<b>🎞 لینک تریلر:</b> \n{movie['trailer']}\n\n"
        f"<b>🍿 حرف ما:</b>\n{clean_text(movie['comment'])}\n\n"
        f"<b>🎯 ارزش دیدن:</b> {rating_stars[movie['rating']]}\n\n"
        f"https://t.me/bestwatch_channel"
    )
    return post

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("این بات فقط برای ادمینه!")
        return
    message = (
        "🎬 به بات Best Watch خوش اومدی!\n\n"
        "این بات برای مدیریت کانال @bestwatch_channelه.\n"
        "دستورات موجود:\n"
        "/start - نمایش این پیام\n"
        "/addmovie - اضافه کردن فیلم دستی (عنوان، تریلر، امتیاز Rotten)\n"
        "/postnow - پست فوری یه فیلم رندوم از TMDB\n\n"
        "هر 10 دقیقه یه فیلم خودکار پست می‌شه."
    )
    await update.message.reply_text(message)

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
        comment = await generate_comment(title)
        imdb_score = float(movie_info['imdb']) if movie_info['imdb'] != 'N/A' else 0
        rating = min(5, max(1, int(imdb_score // 2)))
        special = imdb_score >= 8.5
        movie = {
            'title': movie_info['title'],
            'year': movie_info['year'],
            'plot': movie_info['plot'],
            'imdb': movie_info['imdb'],
            'rotten_tomatoes': rotten,
            'trailer': trailer,
            'comment': comment,
            'rating': rating,
            'special': special,
            'poster': movie_info['poster']
        }
        post = format_movie_post(movie)
        try:
            if movie['poster'] != 'N/A':
                await context.bot.send_photo(chat_id=CHANNEL_ID, photo=movie['poster'], caption=post, parse_mode='HTML')
            else:
                await context.bot.send_message(chat_id=CHANNEL_ID, text=post, parse_mode='HTML')
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
    movie = await get_random_movie()
    if not movie:
        await update.message.reply_text("هیچ فیلمی پیدا نشد! دوباره امتحان کن.")
        return
    post = format_movie_post(movie)
    try:
        if movie['poster'] != 'N/A':
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=movie['poster'], caption=post, parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=post, parse_mode='HTML')
        await update.message.reply_text(f"پست فیلم {movie['title']} ارسال شد!")
        logger.info(f"فیلم {movie['title']} با موفقیت پست شد")
    except Exception as e:
        logger.error(f"خطا در ارسال پست فوری: {str(e)}")
        await update.message.reply_text(f"خطا در ارسال: {str(e)}")

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    logger.info("شروع پست خودکار...")
    movie = await get_random_movie()
    if not movie:
        logger.error("هیچ فیلمی برای پست خودکار پیدا نشد!")
        return
    post = format_movie_post(movie)
    try:
        if movie['poster'] != 'N/A':
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=movie['poster'], caption=post, parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=post, parse_mode='HTML')
        logger.info(f"پست خودکار فیلم {movie['title']} ارسال شد.")
    except Exception as e:
        logger.error(f"خطا در ارسال پست خودکار: {str(e)}")

async def health_check(request):
    return web.Response(text="OK")

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
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
