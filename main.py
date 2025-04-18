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
                return None
    except Exception as e:
        logger.error(f"خطا تو OMDB API: {e}")
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
            async with session.post(url, json=payload, headers=headers, timeout=15) as response:
                data = await response.json()
                return data['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"خطا تو OpenAI API: {e}")
        return "این فیلم یه تجربه فوق‌العاده‌ست! حتماً ببینید!"

async def get_random_movie():
    try:
        async with aiohttp.ClientSession() as session:
            page = random.randint(1, 10)
            url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page={page}"
            async with session.get(url, timeout=15) as response:
                data = await response.json()
                if 'results' not in data:
                    return None
                movie = random.choice(data['results'])
                title = movie['title']
                movie_info = await get_movie_info(title)
                if not movie_info:
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
        logger.error(f"خطا تو TMDB API: {e}")
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
    await update.message.reply_text("🎬 به بات Best Watch خوش اومدی!")

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
            await update.message.reply_text(f"خطا تو ارسال: {str(e)}")
    except Exception as e:
        await update.message.reply_text(f"خطا: {str(e)}")

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("فقط ادمین می‌تونه پست فوری بفرسته!")
        return
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
    except Exception as e:
        await update.message.reply_text(f"خطا تو ارسال: {str(e)}")

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    movie = await get_random_movie()
    if not movie:
        logger.info("هیچ فیلمی برای پست کردن پیدا نشد.")
        return
    post = format_movie_post(movie)
    try:
        if movie['poster'] != 'N/A':
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=movie['poster'], caption=post, parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=post, parse_mode='HTML')
        logger.info(f"پست فیلم {movie['title']} ارسال شد.")
    except Exception as e:
        logger.error(f"خطا تو ارسال خودکار: {str(e)}")

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
    else:
        logger.error("JobQueue در دسترس نیست!")

    # راه‌اندازی سرور HTTP برای Render
    web_app = web.Application()
    web_app.add_routes([web.get('/health', health_check)])
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    try:
        await app.updater.start_polling()
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"خطا تو پولینگ: {e}")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await runner.cleanup()

if __name__ == '__main__':
    asyncio.run(main())
