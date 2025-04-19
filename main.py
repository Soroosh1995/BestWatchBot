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
pip install --upgrade pip
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

# --- فیلم پیش‌فرض برای فال‌بک ---
FALLBACK_MOVIE = {
    'title': 'Inception',
    'year': '2010',
    'plot': 'دزدی که اسرار شرکت‌ها را با فناوری رویا می‌دزدد، باید ایده‌ای در ذهن یک مدیر بکارد. گذشته غم‌انگیز او ممکن است پروژه را به فاجعه بکشاند.',
    'imdb': '8.8/10',
    'rotten_tomatoes': '87%',
    'trailer': 'https://www.youtube.com/watch?v=YoHD9XEInc0',
    'poster': 'https://m.media-amazon.com/images/M/MV5BMjAxMzY3NjcxNF5BMl5BanBnXkFtZTcwNTI5OTM0Mw@@._V1_SX300.jpg',
    'comment': 'اینسپشن، اثری علمی-تخیلی از نولان، با داستانی پیچیده و جلوه‌های بصری خیره‌کننده، ذهن را به چالش می‌کشد. بازی دی‌کاپریو و کارگردانی بی‌نقص، فیلم را فراموش‌نشدنی کرده‌اند. تنها ضعف، ریتم کند برخی صحنه‌هاست که ممکن است برای همه جذاب نباشد. اگر فیلم‌های فکری دوست دارید، اینسپشن را ببینید!',
    'rating': 4,
    'special': True
}

# --- توابع کمکی ---
def clean_text(text):
    """پاکسازی متن برای MarkdownV2"""
    if not text or text == 'N/A':
        return "متن موجود نیست"
    # کاراکترهای خاص MarkdownV2
    chars_to_escape = r'([_\[\]\(\)\~`>#\+-=|\{\}\.!])'
    text = re.sub(chars_to_escape, r'\\\g<1>', text)
    return text[:300]

def shorten_plot(text, max_sentences=3):
    """کوتاه کردن خلاصه داستان به 2-3 جمله"""
    sentences = text.split('. ')
    return '. '.join(sentences[:max_sentences])[:100]

def is_farsi(text):
    """چک کردن فارسی بودن متن"""
    farsi_chars = r'[\u0600-\u06FF]'
    return bool(re.search(farsi_chars, text))

async def translate_title_to_english(title):
    """ترجمه عنوان فارسی به انگلیسی با TMDB"""
    try:
        async with aiohttp.ClientSession() as session:
            search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}&language=en-US"
            async with session.get(search_url) as response:
                data = await response.json()
                if data.get('results'):
                    return data['results'][0].get('title', title)
                return title
    except Exception as e:
        logger.error(f"خطا در ترجمه عنوان {title}: {str(e)}")
        return title

async def get_movie_info(title):
    """دریافت اطلاعات فیلم از TMDB و OMDB با فال‌بک"""
    logger.info(f"دریافت اطلاعات برای فیلم: {title}")
    try:
        async with aiohttp.ClientSession() as session:
            # TMDB برای خلاصه، تریلر، و اطلاعات اولیه
            search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}&language=fa-IR"
            async with session.get(search_url) as tmdb_response:
                tmdb_data = await tmdb_response.json()
                if not tmdb_data.get('results'):
                    logger.warning(f"TMDB هیچ نتیجه‌ای برای {title} نداد")
                    tmdb_plot = ""
                    movie_id = None
                    tmdb_title = title
                    tmdb_year = 'N/A'
                else:
                    tmdb_plot = tmdb_data['results'][0].get('overview', '')
                    movie_id = tmdb_data['results'][0].get('id')
                    tmdb_title = tmdb_data['results'][0].get('title', title)
                    tmdb_year = tmdb_data['results'][0].get('release_date', 'N/A')[:4]
                
                trailer = "N/A"
                if movie_id:
                    videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
                    async with session.get(videos_url) as videos_response:
                        videos_data = await videos_response.json()
                        if videos_data.get('results'):
                            for video in videos_data['results']:
                                if video['type'] == 'Trailer' and video['site'] == 'YouTube':
                                    trailer = f"https://www.youtube.com/watch?v={video['key']}"
                                    break
            
            # OMDB برای پوستر، امتیاز، و خلاصه فال‌بک
            omdb_data = None
            try:
                # ترجمه عنوان به انگلیسی برای OMDB
                omdb_title = await translate_title_to_english(title)
                omdb_url = f"http://www.omdbapi.com/?t={omdb_title}&apikey={OMDB_API_KEY}"
                async with session.get(omdb_url) as response:
                    omdb_data = await response.json()
                    if omdb_data.get('Response') != 'True':
                        logger.error(f"OMDB پاسخ معتبر نداد برای {omdb_title}: {omdb_data.get('Error')}")
                        omdb_data = None
            except Exception as e:
                logger.error(f"خطا در درخواست OMDB برای {title}: {str(e)}")
                omdb_data = None
            
            # انتخاب خلاصه داستان
            plot = ""
            if tmdb_plot and is_farsi(tmdb_plot):
                plot = shorten_plot(tmdb_plot)
                logger.info(f"خلاصه فارسی از TMDB برای {title}")
            elif omdb_data and omdb_data.get('Plot') and is_farsi(omdb_data.get('Plot')):
                plot = shorten_plot(omdb_data.get('Plot'))
                logger.info(f"خلاصه فارسی از OMDB برای {title}")
            else:
                plot = "داستان فیلم درباره‌ی یک ماجراجویی هیجان‌انگیز است که شما را شگفت‌زده می‌کند."
                logger.info(f"فال‌بک خلاصه برای {title}")
            
            # اطلاعات نهایی
            info = {
                'title': tmdb_title,
                'year': tmdb_year,
                'plot': plot,
                'imdb': omdb_data.get('imdbRating', 'N/A') + '/10' if omdb_data and omdb_data.get('imdbRating') else 'N/A',
                'rotten_tomatoes': next(
                    (r['Value'] for r in omdb_data.get('Ratings', []) if omdb_data and r['Source'] == 'Rotten Tomatoes'),
                    'N/A'
                ),
                'trailer': trailer,
                'poster': omdb_data.get('Poster', 'N/A') if omdb_data and omdb_data.get('Poster') else 'N/A'
            }
            return info
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات فیلم {title}: {str(e)}")
        return None

async def generate_comment(title):
    """تولید تحلیل با OpenAI یا فال‌بک پیش‌فرض"""
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
                return f"تحلیل موقت: {title} فیلمی جذاب با داستانی گیرا و بازیگری قوی است. کارگردانی حرفه‌ای آن شما را سرگرم می‌کند، هرچند ممکن است برخی صحنه‌ها کمی کند باشند. حتماً تماشا کنید!"
    except Exception as e:
        logger.error(f"خطا در تولید تحلیل برای {title}: {str(e)}")
        return f"تحلیل موقت: {title} فیلمی جذاب با داستانی گیرا و بازیگری قوی است. کارگردانی حرفه‌ای آن شما را سرگرم می‌کند، هرچند ممکن است برخی صحنه‌ها کمی کند باشند. حتماً تماشا کنید!"

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
                    cached_movies = [
                        {'title': m['title'], 'id': m['id']}
                        for m in data['results']
                        if m.get('title') and m.get('id')
                    ]
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

async def get_random_movie(max_retries=3):
    """انتخاب فیلم تصادفی با تلاش مجدد"""
    logger.info("انتخاب فیلم تصادفی...")
    for attempt in range(max_retries):
        try:
            if not cached_movies or (datetime.now() - last_fetch_time).seconds > 86400:
                logger.info("کش خالی یا قدیمی، آپدیت کش...")
                await fetch_movies_to_cache()
            
            if not cached_movies:
                logger.error("هیچ فیلمی در کش موجود نیست، استفاده از فال‌بک")
                return FALLBACK_MOVIE
            
            movie = random.choice(cached_movies)
            logger.info(f"فیلم انتخاب شد: {movie['title']} (تلاش {attempt + 1})")
            movie_info = await get_movie_info(movie['title'])
            if not movie_info:
                logger.warning(f"اطلاعات فیلم {movie['title']} دریافت نشد، تلاش مجدد...")
                continue
            
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
            logger.error(f"خطا در انتخاب فیلم (تلاش {attempt + 1}): {str(e)}")
            if attempt == max_retries - 1:
                logger.error("تلاش‌ها تمام شد، استفاده از فال‌بک")
                return FALLBACK_MOVIE
            continue
    logger.error("تلاش‌ها تمام شد، استفاده از فال‌بک")
    return FALLBACK_MOVIE

def format_movie_post(movie):
    """فرمت پست دقیقاً مثل نمونه درخواستی"""
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
/testapis - تست APIهای TMDB و OMDB
/resetwebhook - ریست Webhook تلگرام
""")

async def reset_webhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ریست Webhook تلگرام"""
    if str(update.message.from_user.id) == ADMIN_ID:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
                    json={"drop_pending_updates": True}
                ) as response:
                    result = await response.json()
                    if result.get('ok'):
                        await update.message.reply_text("✅ Webhook ریست شد")
                    else:
                        await update.message.reply_text(f"❌ خطا در ریست Webhook: {result.get('description')}")
        except Exception as e:
            logger.error(f"خطا در ریست Webhook: {e}")
            await update.message.reply_text(f"❌ خطا در ریست Webhook: {str(e)}")

async def test_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تست دسترسی به کانال"""
    if str(update.message.from_user.id) == ADMIN_ID:
        try:
            await context.bot.send_message(CHANNEL_ID, "تست دسترسی بات")
            await update.message.reply_text("✅ پیام تست به کانال ارسال شد")
        except Exception as e:
            logger.error(f"خطا در دسترسی به کانال: {e}")
            await update.message.reply_text(f"❌ خطا در دسترسی به کانال: {str(e)}")

async def test_apis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تست APIهای TMDB و OMDB"""
    if str(update.message.from_user.id) == ADMIN_ID:
        msg = await update.message.reply_text("در حال تست APIها...")
        try:
            async with aiohttp.ClientSession() as session:
                # TMDB
                tmdb_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=fa-IR&page=1"
                async with session.get(tmdb_url) as tmdb_res:
                    tmdb_data = await tmdb_res.json()
                    tmdb_status = "✅ TMDB اوکی" if tmdb_data.get('results') else f"❌ TMDB خطا: {tmdb_data}"
                
                # OMDB
                omdb_status = "❌ OMDB غیرفعال یا خطا"
                try:
                    omdb_url = f"http://www.omdbapi.com/?t=Inception&apikey={OMDB_API_KEY}"
                    async with session.get(omdb_url) as omdb_res:
                        omdb_data = await omdb_res.json()
                        omdb_status = "✅ OMDB اوکی" if omdb_data.get('Response') == 'True' else f"❌ OMDB خطا: {omdb_data.get('Error')}"
                except Exception as e:
                    omdb_status = f"❌ OMDB خطا: {str(e)}"
                
                # OpenAI
                openai_status = "❌ OpenAI غیرفعال یا خطا"
                try:
                    headers = {"Authorization": f"Bearer {OPENAI_API_KEY.strip()}", "Content-Type": "application/json"}
                    payload = {"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "تست"}]}
                    async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload) as openai_res:
                        openai_data = await openai_res.json()
                        openai_status = "✅ OpenAI اوکی" if 'choices' in openai_data else f"❌ OpenAI خطا: {openai_data.get('error', {}).get('message', 'خطای ناشناخته')}"
                except Exception as e:
                    openai_status = f"❌ OpenAI خطا: {str(e)}"
                
                await msg.edit_text(f"{tmdb_status}\n{omdb_status}\n{openai_status}")
        except Exception as e:
            logger.error(f"خطا در تست APIها: {e}")
            await msg.edit_text(f"❌ خطا در تست APIها: {str(e)}")

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
                if movie['poster'] != 'N/A' and movie['poster'].startswith('http'):
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
            if movie['poster'] != 'N/A' and movie['poster'].startswith('http'):
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

async def run_bot():
    """راه‌اندازی بات تلگرام"""
    logger.info("شروع راه‌اندازی بات تلگرام...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fetchmovies", fetch_movies))
    app.add_handler(CommandHandler("postnow", post_now))
    app.add_handler(CommandHandler("testchannel", test_channel))
    app.add_handler(CommandHandler("testapis", test_apis))
    app.add_handler(CommandHandler("resetwebhook", reset_webhook))
    
    job_queue = app.job_queue
    if job_queue:
        logger.info("JobQueue فعال شد")
        job_queue.run_repeating(auto_post, interval=7200, first=10)  # هر 2 ساعت
    else:
        logger.error("JobQueue فعال نشد")
        await app.bot.send_message(ADMIN_ID, "❌ خطا: JobQueue فعال نشد")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    return app

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
