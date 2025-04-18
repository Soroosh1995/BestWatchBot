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
from datetime import datetime, time

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
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
PORT = int(os.getenv('PORT', 8080))

# --- کش فیلم‌ها ---
cached_movies = []
last_fetch_time = None

# --- توابع کمکی ---
def clean_text(text):
    """پاکسازی متن برای MarkdownV2"""
    if not text or text == 'N/A':
        return "متن موجود نیست"
    # اسکیپ کاراکترهای خاص
    chars_to_escape = r'[_*[]()~`>#+-=|{}.!]'
    text = re.sub(chars_to_escape, r'\\\g<0>', text)
    return text[:300]

def shorten_plot(text, max_sentences=3):
    """کوتاه کردن خلاصه داستان به 2-3 جمله"""
    sentences = text.split('. ')
    return '. '.join(sentences[:max_sentences])[:100]

def is_farsi(text):
    """چک کردن فارسی بودن متن"""
    farsi_chars = r'[\u0600-\u06FF]'
    return bool(re.search(farsi_chars, text))

async def get_movie_info(title):
    """دریافت اطلاعات فیلم از TMDB و OMDB"""
    logger.info(f"دریافت اطلاعات برای فیلم: {title}")
    try:
        async with aiohttp.ClientSession() as session:
            # TMDB برای خلاصه و تریلر
            search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
            async with session.get(search_url) as tmdb_response:
                tmdb_data = await tmdb_response.json()
                tmdb_plot = tmdb_data.get('results', [{}])[0].get('overview', '')
                
                trailer = "N/A"
                if tmdb_data.get('results'):
                    movie_id = tmdb_data['results'][0]['id']
                    videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
                    async with session.get(videos_url) as videos_response:
                        videos_data = await videos_response.json()
                        if videos_data.get('results'):
                            for video in videos_data['results']:
                                if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                    trailer = f"https://www.youtube.com/watch?v={video['key']}"
                                    break
            
            # OMDB برای پوستر، امتیاز، و خلاصه فال‌بک
            omdb_url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
            async with session.get(omdb_url) as response:
                omdb_data = await response.json()
                
                if omdb_data.get('Response') != 'True':
                    logger.error(f"OMDB پاسخ معتبر نداد برای {title}")
                    return None
                
                # انتخاب خلاصه داستان
                plot = ""
                if tmdb_plot and is_farsi(tmdb_plot):
                    plot = shorten_plot(tmdb_plot)
                elif omdb_data.get('Plot') and is_farsi(omdb_data.get('Plot')):
                    plot = shorten_plot(omdb_data.get('Plot'))
                else:
                    plot = "داستان فیلم درباره‌ی یک ماجراجویی هیجان‌انگیز است که شما را شگفت‌زده می‌کند."
                
                imdb_rating = f"{float(omdb_data.get('imdbRating', 0)):.1f}/10"
                rt_rating = next(
                    (r['Value'] for r in omdb_data.get('Ratings', []) 
                    if r['Source'] == 'Rotten Tomatoes'), 'N/A')
                
                return {
                    'title': omdb_data.get('Title', title),
                    'year': omdb_data.get('Year', 'N/A'),
                    'plot': plot,
                    'imdb': imdb_rating,
                    'rotten_tomatoes': rt_rating,
                    'trailer': trailer,
                    'poster': omdb_data.get('Poster', 'N/A')
                }
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات فیلم {title}: {e}")
        return None

async def generate_comment(title):
    """تولید تحلیل با OpenAI (80-100 کلمه)"""
    logger.info(f"تولید تحلیل برای فیلم: {title}")
    try:
        prompt = f"""
        تحلیل حرفه‌ای و جذاب درباره فیلم {title} به زبان فارسی، دقیقاً 80-100 کلمه:
        1. معرفی کوتاه فیلم و ژانر آن
        2. نقاط قوت اصلی (مثل داستان، بازیگری، کارگردانی)
        3. یک ضعف کوچک
        4. توصیه برای تماشا
        لحن سینمایی و حرفه‌ای باشد. از تکرار ایده‌های کلیشه‌ای پرهیز کن.
        مثال: اینسپشن شاهکاری از نولان است که با داستان پیچیده و جلوه‌های بصری خیره‌کننده، ذهن را به چالش می‌کشد...
        """
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY.strip()}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 200
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                data = await response.json()
                if 'choices' in data:
                    return clean_text(data['choices'][0]['message']['content'])
                logger.error(f"OpenAI پاسخ معتبر نداد: {data}")
                return "تحلیل موقت: این فیلم با داستان جذاب و بازیگری قوی، ارزش تماشا دارد، هرچند ممکن است پایانش کمی گنگ باشد."
    except Exception as e:
        logger.error(f"خطا در تولید تحلیل برای {title}: {e}")
        return "تحلیل موقت: این فیلم یک تجربه سینمایی متفاوت است که شما را سرگرم خواهد کرد."

async def fetch_movies_to_cache():
    """آپدیت کش فیلم‌ها از TMDB"""
    global cached_movies, last_fetch_time
    logger.info("شروع آپدیت کش فیلم‌ها...")
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=fa-IR&page=1"
            async with session.get(url) as response:
                data = await response.json()
                if 'results' in data and data['results']:
                    cached_movies = data['results']
                    last_fetch_time = datetime.now()
                    logger.info(f"لیست فیلم‌ها آپدیت شد. تعداد: {len(cached_movies)}")
                    return True
                logger.error("داده‌ای از TMDB دریافت نشد")
                cached_movies = [{'title': 'Inception'}, {'title': 'The Matrix'}]
                last_fetch_time = datetime.now()
                return False
    except Exception as e:
        logger.error(f"خطا در آپدیت کش: {e}")
        cached_movies = [{'title': 'Inception'}, {'title': 'The Matrix'}]
        last_fetch_time = datetime.now()
        return False

async def get_random_movie():
    """انتخاب فیلم تصادفی"""
    logger.info("انتخاب فیلم تصادفی...")
    try:
        if not cached_movies or (datetime.now() - last_fetch_time).seconds > 86400:
            logger.info("کش خالی یا قدیمی، آپدیت کش...")
            await fetch_movies_to_cache()
        
        movie = random.choice(cached_movies)
        logger.info(f"فیلم انتخاب شد: {movie['title']}")
        movie_info = await get_movie_info(movie['title'])
        if not movie_info:
            logger.error("اطلاعات فیلم دریافت نشد")
            return None
        
        comment = await generate_comment(movie['title'])
        imdb_score = float(movie_info['imdb'].split('/')[0]) if movie_info['imdb'] != 'N/A' else 0
        
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
        logger.error(f"خطا در انتخاب فیلم: {e}")
        return None

def format_movie_post(movie):
    """فرمت پست مطابق نمونه درخواستی"""
    stars = '⭐️' * movie['rating']
    special = ' 👑' if movie['special'] else ''
    channel_link = 'https://t.me/bestwatch_channel'
    
    return f"""
🎬 **عنوان فیلم: {clean_text(movie['title'])}{special}**

📅 **سال تولید: {clean_text(movie['year'])}**

📝 **خلاصه داستان:**
{clean_text(movie['plot'])}

🌟 **امتیاز:**
**IMDB: {clean_text(movie['imdb'])}**
**Rotten Tomatoes: {clean_text(movie['rotten_tomatoes'])}**

🎞 **لینک تریلر:**
{clean_text(movie['trailer'])}

🍿 **حرف ما:**
{clean_text(movie['comment'])}

🎯 **ارزش دیدن: {stars}**

{channel_link}
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع برای ادمین"""
    if str(update.message.from_user.id) == ADMIN_ID:
        await update.message.reply_text("""
🤖 دستورات ادمین:
/fetchmovies - آپدیت لیست فیلم‌ها
/postnow - ارسال پست فوری
/testchannel - تست دسترسی به کانال
""")

async def test_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تست دسترسی به کانال"""
    if str(update.message.from_user.id) == ADMIN_ID:
        try:
            await context.bot.send_message(CHANNEL_ID, "تست دسترسی بات")
            await update.message.reply_text("✅ پیام تست به کانال ارسال شد")
        except Exception as e:
            logger.error(f"خطا در دسترسی به کانال: {e}")
            await update.message.reply_text(f"❌ خطا در دسترسی به کانال: {str(e)}")

async def fetch_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آپدیت دستی کش فیلم‌ها"""
    if str(update.message.from_user.id) == ADMIN_ID:
        msg = await update.message.reply_text("در حال آپدیت لیست...")
        if await fetch_movies_to_cache():
            await msg.edit_text(f"✅ لیست آپدیت شد! ({len(cached_movies)} فیلم)")
        else:
            await msg.edit_text("❌ خطا در آپدیت لیست")

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال پست دستی"""
    if str(update.message.from_user.id) == ADMIN_ID:
        msg = await update.message.reply_text("در حال آماده‌سازی پست...")
        movie = await get_random_movie()
        if movie:
            try:
                if movie['poster'] != 'N/A':
                    await context.bot.send_photo(
                        chat_id=CHANNEL_ID,
                        photo=movie['poster'],
                        caption=format_movie_post(movie),
                        parse_mode='MarkdownV2'
                    )
                else:
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=format_movie_post(movie),
                        parse_mode='MarkdownV2'
                    )
                await msg.edit_text(f"✅ پست {movie['title']} ارسال شد")
            except Exception as e:
                logger.error(f"خطا در ارسال پست: {e}")
                await msg.edit_text(f"❌ خطا در ارسال پست: {str(e)}")
        else:
            await msg.edit_text("❌ خطا در یافتن فیلم")

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    """ارسال پست خودکار"""
    logger.info("شروع پست خودکار...")
    movie = await get_random_movie()
    if movie:
        logger.info(f"فیلم انتخاب شد: {movie['title']}")
        try:
            if movie['poster'] != 'N/A':
                await context.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=movie['poster'],
                    caption=format_movie_post(movie),
                    parse_mode='MarkdownV2'
                )
            else:
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=format_movie_post(movie),
                    parse_mode='MarkdownV2'
                )
            logger.info(f"پست خودکار برای {movie['title']} ارسال شد")
        except Exception as e:
            logger.error(f"خطا در ارسال پست خودکار: {e}")
            await context.bot.send_message(ADMIN_ID, f"❌ خطای پست خودکار: {str(e)}")
    else:
        logger.error("فیلم برای پست خودکار یافت نشد")
        await context.bot.send_message(ADMIN_ID, "❌ خطا: فیلم برای پست خودکار یافت نشد")

async def health_check(request):
    """چک سلامت سرور"""
    return web.Response(text="OK")

async def main():
    """راه‌اندازی بات"""
    logger.info("شروع راه‌اندازی بات...")
    if not await fetch_movies_to_cache():
        logger.error("خطا در دریافت اولیه لیست فیلم‌ها")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fetchmovies", fetch_movies))
    app.add_handler(CommandHandler("postnow", post_now))
    app.add_handler(CommandHandler("testchannel", test_channel))
    
    job_queue = app.job_queue
    if job_queue:
        logger.info("JobQueue فعال شد")
        job_queue.run_repeating(auto_post, interval=600, first=10)
    else:
        logger.error("JobQueue فعال نشد")
        await app.bot.send_message(ADMIN_ID, "❌ خطا: JobQueue فعال نشد")
    
    runner = web.AppRunner(web.Application())
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    await app.run_polling()
    logger.info("🤖 ربات با موفقیت راه‌اندازی شد")

if __name__ == '__main__':
    asyncio.run(main())
