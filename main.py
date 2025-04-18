import telegram
import asyncio
import json
import os
import logging
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
import re

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
ADMIN_ID = os.getenv('ADMIN_ID')
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

MOVIES_FILE = 'movies.json'

def load_movies():
    try:
        with open(MOVIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_movies(movies):
    with open(MOVIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(movies, f, ensure_ascii=False, indent=4)

def is_movie_duplicate(title, movies):
    return any(movie['title'].lower() == title.lower() for movie in movies)

async def get_movie_info(title):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            async with session.get(url, timeout=10) as response:
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
            async with session.post(url, json=payload, headers=headers, timeout=10) as response:
                data = await response.json()
                return data['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"خطا تو OpenAI API: {e}")
        return "این فیلم یه تجربه فوق‌العاده‌ست! حتماً ببینید!"

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
        movies = load_movies()
        if is_movie_duplicate(title, movies):
            await update.message.reply_text(f"فیلم {title} قبلاً اضافه شده!")
            return
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
        movies.append(movie)
        save_movies(movies)
        await update.message.reply_text(f"فیلم {movie['title']} اضافه شد!")
    except Exception as e:
        await update.message.reply_text(f"خطا: {str(e)}")

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != ADMIN_ID:
        await update.message.reply_text("فقط ادمین می‌تونه پست فوری بفرسته!")
        return
    movies = load_movies()
    if not movies:
        await update.message.reply_text("هیچ فیلمی تو دیتابیس نیست!")
        return
    movie = movies.pop(0)
    save_movies(movies)
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
    movies = load_movies()
    if not movies:
        logger.info("هیچ فیلمی برای پست کردن نیست.")
        return
    movie = movies.pop(0)
    save_movies(movies)
    post = format_movie_post(movie)
    try:
        if movie['poster'] != 'N/A':
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=movie['poster'], caption=post, parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=post, parse_mode='HTML')
        logger.info(f"پست فیلم {movie['title']} ارسال شد.")
    except Exception as e:
        logger.error(f"خطا تو ارسال خودکار: {str(e)}")

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addmovie", add_movie))
    app.add_handler(CommandHandler("postnow", post_now))
    async def schedule_posts():
        while True:
            try:
                await auto_post(app)
                await asyncio.sleep(600)  # هر 10 دقیقه
            except Exception as e:
                logger.error(f"خطا تو زمان‌بندی: {e}")
                await asyncio.sleep(60)
    app.create_task(schedule_posts())
    await app.initialize()
    await app.start()
    try:
        await app.updater.start_polling()
    finally:
        await app.stop()
        await app.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
