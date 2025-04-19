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
import openai

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
openai.api_key = OPENAI_API_KEY

# --- کش و متغیرهای سراسری ---
cached_movies = []
posted_movies = []
last_fetch_time = None
previous_plots = []
previous_comments = []
gemini_available = True
openai_available = True
bot_enabled = True  # وضعیت ربات (فعال/غیرفعال)

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

# --- فال‌بک‌های خلاصه داستان بر اساس ژانر ---
FALLBACK_PLOTS = {
    'اکشن': [
        "ماجراجویی پرهیجانی که قهرمان با دشمنان قدرتمند روبرو می‌شود. نبردهای نفس‌گیر شما را میخکوب می‌کند. آیا او می‌تواند جهان را نجات دهد؟",
        "داستانی پر از تعقیب و گریز و انفجارهای مهیج. یک سرباز شجاع در برابر تهدیدی بزرگ ایستادگی می‌کند. پایان این نبرد چه خواهد بود؟",
        "جهانی در آستانه نابودی و یک جنگجوی تنها. ماموریتی خطرناک برای بازگرداندن صلح آغاز می‌شود. شجاعت او همه‌چیز را تغییر می‌دهد.",
        "دشمنی قدیمی دوباره شعله‌ور می‌شود. مبارزه‌ای بی‌امان برای عدالت در جریان است. آیا قهرمان می‌تواند پیروز شود؟",
        "یک مامور مخفی در دنیایی پر از خطر. نقشه‌ای شوم که باید خنثی شود. هیجان در هر لحظه موج می‌زند.",
        "جهانی پر از هرج‌ومرج و یک ناجی غیرمنتظره. نبردی برای بقا که همه را شگفت‌زده می‌کند. آیا امید زنده می‌ماند؟",
        "گروهی از مبارزان در برابر نیروی تاریک. اتحاد آن‌ها تنها راه پیروزی است. این داستان شما را به وجد می‌آورد.",
        "قهرمانی که گذشته‌اش را رها کرده، دوباره به میدان بازمی‌گردد. دشمنی قدرتمند در انتظار اوست. پایان این جنگ چه خواهد بود؟",
        "ماجراجویی در دل خطر با اکشن بی‌وقفه. یک هدف بزرگ و یک اراده قوی. این داستان شما را سرجایتان میخکوب می‌کند.",
        "جهانی که قانون در آن غریب است. یک فرد عادی که به قهرمان تبدیل می‌شود. مبارزه برای عدالت آغاز شده است."
    ],
    'درام': [
        "داستانی عمیق از روابط انسانی و انتخاب‌های سخت. زندگی شخصیتی پیچیده که قلب شما را لمس می‌کند. آیا او راه خود را پیدا خواهد کرد؟",
        "خانواده‌ای که با رازهای گذشته روبرو می‌شود. عشق و فداکاری در برابر آزمون زمان. این داستان شما را به فکر فرو می‌برد.",
        "زندگی‌ای پر از پستی و بلندی و تصمیم‌های سرنوشت‌ساز. یک سفر احساسی که اشک و لبخند را باهم می‌آورد. پایان این مسیر چیست؟",
        "دوستی که در برابر مشکلات آزمایش می‌شود. لحظاتی از شادی و غم که قلب را تسخیر می‌کند. آیا این پیوند پایدار می‌ماند؟",
        "مردی که با گذشته‌اش می‌جنگد تا آینده‌ای بهتر بسازد. انتخاب‌هایی که زندگی را تغییر می‌دهند. این داستان شما را تکان خواهد داد.",
        "زنی که در جستجوی هویت خود است. موانعی که او را قوی‌تر می‌کنند. آیا او به آرامش می‌رسد؟",
        "داستانی از عشق ممنوعه و آرزوهای بربادرفته. لحظاتی که قلب را می‌شکنند و می‌سازند. پایان این عشق چیست؟",
        "زندگی‌ای که با یک تصمیم تغییر می‌کند. مبارزه‌ای برای رستگاری و بخشش. این داستان شما را به فکر وا می‌دارد.",
        "خانواده‌ای که دوباره دور هم جمع می‌شوند. رازهایی که فاش می‌شوند و پیوندها را آزمایش می‌کنند. آیا عشق پیروز می‌شود؟",
        "جوانی که در جستجوی معنای زندگی است. مسیری پر از چالش و کشف خود. این داستان شما را الهام می‌بخشد."
    ],
    'کمدی': [
        "ماجراهای خنده‌داری که زندگی را زیرورو می‌کنند. گروهی از دوستان که در موقعیت‌های عجیب گیر می‌افتند. آیا از این مخمصه خلاص می‌شوند؟",
        "سوءتفاهم‌های بامزه‌ای که همه را به خنده می‌اندازد. یک روز معمولی که به هرج‌ومرج تبدیل می‌شود. پایان این داستان چیست؟",
        "شخصیتی عجیب که همه را به دردسر می‌اندازد. لحظاتی پر از خنده و شادی. آیا او درسش را یاد می‌گیرد؟",
        "ماجرای یک اشتباه بزرگ و تلاش برای درست کردنش. کمدی‌ای که شما را از خنده روده‌بر می‌کند. پایان این ماجرا چطور خواهد بود؟",
        "دو دوست که در موقعیت‌های خنده‌دار گیر می‌افتند. نقشه‌هایی که همیشه خراب می‌شوند. این داستان شما را شاد خواهد کرد.",
        "خانواده‌ای که هرگز روز آرامی ندارند. شوخی‌ها و موقعیت‌های بامزه‌ای که غیرقابل‌پیش‌بینی‌اند. آیا آرامش به آن‌ها بازمی‌گردد؟",
        "ماجراجویی‌ای که با یک شوخی شروع می‌شود. اتفاقات خنده‌داری که همه را غافلگیر می‌کند. این کمدی شما را سرگرم خواهد کرد.",
        "شخصی که فکر می‌کند همه‌چیز را می‌داند، اما همیشه اشتباه می‌کند. لحظاتی که خنده را به لب‌هایتان می‌آورد. آیا او تغییر می‌کند؟",
        "داستانی پر از شوخی‌های بامزه و موقعیت‌های عجیب. گروهی که همیشه در دردسرند. این داستان شما را به خنده می‌اندازد.",
        "یک روز عادی که به یک کمدی بزرگ تبدیل می‌شود. نقشه‌های خنده‌داری که همه را گیج می‌کنند. پایان این ماجرا چیست؟"
    ],
    'علمی-تخیلی': [
        "جهانی در آینده که تکنولوژی همه‌چیز را تغییر داده. ماجراجویی‌ای برای کشف حقیقت پشت یک راز بزرگ. آیا بشریت نجات پیدا می‌کند؟",
        "سفری به سیاره‌ای ناشناخته با خطرات غیرمنتظره. گروهی از کاوشگران که با ناشناخته‌ها روبرو می‌شوند. این ماجرا به کجا ختم می‌شود؟",
        "جهانی که هوش مصنوعی بر آن حاکم است. یک انسان در برابر ماشینی قدرتمند. آیا او می‌تواند سرنوشت را تغییر دهد؟",
        "داستانی از سفر در زمان و عواقب آن. انتخاب‌هایی که تاریخ را تغییر می‌دهند. پایان این سفر چیست؟",
        "جهانی که در آن واقعیت و رویا یکی شده‌اند. مبارزه‌ای برای کشف حقیقت. این داستان شما را شگفت‌زده خواهد کرد.",
        "تمدنی پیشرفته که با تهدیدی عظیم روبروست. یک قهرمان غیرمنتظره که همه‌چیز را تغییر می‌دهد. آیا امید زنده می‌ماند؟",
        "اکتشافی در فضا که رازهای کیهانی را فاش می‌کند. خطراتی که بشریت را به چالش می‌کشند. این ماجرا شما را میخکوب می‌کند.",
        "جهانی که در آن انسان‌ها دیگر تنها نیستند. رویارویی با موجوداتی ناشناخته. پایان این داستان چیست؟",
        "فناوری‌ای که وعده بهشت می‌دهد، اما تاریکی به همراه دارد. مبارزه‌ای برای نجات بشریت. آیا حقیقت پیروز می‌شود؟",
        "سفری به بعدی دیگر با قوانین ناشناخته. گروهی که باید برای بقا بجنگند. این داستان شما را به فکر فرو می‌برد."
    ]
}

# --- فال‌بک‌های حرف ما بر اساس ژانر ---
FALLBACK_COMMENTS = {
    'اکشن': [
        "این فیلم با صحنه‌های اکشن نفس‌گیر و داستان پرهیجان، شما را به صندلی میخکوب می‌کند. کارگردانی پویا و جلوه‌های بصری خیره‌کننده از نقاط قوت آن است. فقط گاهی ریتم تند ممکن است کمی گیج‌کننده باشد.",
        "داستانی پر از هیجان و نبردهای حماسی که لحظه‌ای آرامش ندارد. بازیگران با انرژی فوق‌العاده‌ای نقش‌آفرینی کرده‌اند. اگر عاشق اکشن بی‌وقفه هستید، این فیلم برای شماست.",
        "این اثر با تعقیب و گریزهای مهیج و داستان جذاب، شما را سرگرم می‌کند. موسیقی متن قدرتمند به هیجان آن افزوده است. فقط برخی کلیشه‌ها ممکن است تکراری به نظر برسند.",
        "فیلمی که نبض شما را تندتر می‌کند و اکشن را به سطح جدیدی می‌برد. طراحی صحنه‌های مبارزه بی‌نظیر است. گاهی داستان فرعی کمی گم می‌شود.",
        "این فیلم ترکیبی از اکشن و هیجان است که لحظه‌ای شما را رها نمی‌کند. شخصیت‌پردازی قوی و جلوه‌های ویژه تماشایی‌اند. فقط پایانش ممکن است کمی قابل‌پیش‌بینی باشد.",
        "اکشنی که با ریتم تند و داستان گیرا شما را مجذوب می‌کند. کارگردانی استادانه و بازیگری قابل‌توجه از نقاط قوت آن است. برخی دیالوگ‌ها می‌توانستند قوی‌تر باشند.",
        "این فیلم با صحنه‌های اکشن خلاقانه و داستان پرکشش، تجربه‌ای فراموش‌نشدنی است. موسیقی متن به‌خوبی حس هیجان را منتقل می‌کند. فقط برخی پیچش‌ها ممکن است غیرمنتظره نباشند.",
        "داستانی پر از انفجار و هیجان که شما را در لحظه نگه می‌دارد. طراحی صحنه‌های اکشن بسیار حرفه‌ای است. گاهی عمق داستان قربانی سرعت می‌شود.",
        "این اثر با اکشن بی‌امان و داستان جذاب، شما را سرگرم خواهد کرد. بازیگران شیمی فوق‌العاده‌ای دارند. فقط برخی جزئیات داستانی می‌توانستند بهتر توضیح داده شوند.",
        "فیلمی پر از انرژی و هیجان که لحظه‌ای کسل‌کننده نیست. جلوه‌های بصری و کارگردانی از نقاط قوت آن هستند. پایان‌بندی می‌توانست کمی خلاقانه‌تر باشد."
    ],
    'درام': [
        "این فیلم با داستانی عمیق و احساسی، قلب شما را تسخیر می‌کند. بازیگری بی‌نقص و کارگردانی حساس، آن را به اثری ماندگار تبدیل کرده‌اند. فقط ریتم کند برخی صحنه‌ها ممکن است صبر شما را بیازماید.",
        "داستانی که روابط انسانی را با ظرافت به تصویر می‌کشد. موسیقی متن احساسی و فیلم‌برداری زیبا به عمق داستان افزوده‌اند. گاهی پایان‌بندی کمی باز می‌ماند.",
        "این اثر با شخصیت‌پردازی قوی و داستان پراحساس، شما را به فکر فرو می‌برد. دیالوگ‌های معنادار و بازیگری فوق‌العاده از نقاط قوت آن هستند. فقط برخی لحظات ممکن است بیش از حد غم‌انگیز باشند.",
        "فیلمی که با داستان تکان‌دهنده و بازیگری عمیق، احساسات شما را برمی‌انگیزد. کارگردانی دقیق و موسیقی متن تأثیرگذار است. فقط برخی پیچش‌های داستانی می‌توانستند قوی‌تر باشند.",
        "این داستان احساسی با لحظاتی از شادی و غم، شما را همراه خود می‌برد. فیلم‌برداری هنرمندانه و بازیگرانی عالی دارد. گاهی ریتم داستان کمی کند می‌شود.",
        "داستانی که شما را با شخصیت‌هایش همزادپنداری می‌کند. کارگردانی بااحساس و دیالوگ‌های قوی از نقاط قوت آن است. فقط برخی صحنه‌ها ممکن است طولانی به نظر برسند.",
        "این فیلم با داستانی عمیق و بازیگری تأثیرگذار، شما را مجذوب می‌کند. موسیقی متن به‌خوبی حس صحنه‌ها را منتقل می‌کند. پایان‌بندی می‌توانست کمی روشن‌تر باشد.",
        "داستانی از زندگی واقعی که قلب و ذهن شما را درگیر می‌کند. بازیگران با نقش‌آفرینی درخشان، داستان را زنده کرده‌اند. فقط برخی لحظات ممکن است پیش‌بینی‌پذیر باشند.",
        "این اثر با داستانی احساسی و شخصیت‌های پیچیده، شما را به فکر وا می‌دارد. کارگردانی استادانه و فیلم‌برداری زیبا از نقاط قوت آن است. فقط ریتم برخی بخش‌ها می‌توانست سریع‌تر باشد.",
        "فیلمی که با داستان عمیق و بازیگری قوی، شما را تحت تأثیر قرار می‌دهد. موسیقی متن احساسی و دیالوگ‌های معنادار آن را خاص کرده‌اند. فقط برخی جزئیات داستانی می‌توانستند واضح‌تر باشند."
    ],
    'کمدی': [
        "این فیلم با شوخی‌های بامزه و داستان سرگرم‌کننده، شما را به خنده می‌اندازد. بازیگران شیمی فوق‌العاده‌ای دارند و کارگردانی پرانرژی است. فقط برخی جوک‌ها ممکن است تکراری به نظر برسند.",
        "کمدی‌ای که با موقعیت‌های خنده‌دار و دیالوگ‌های بامزه، شما را سرگرم می‌کند. ریتم تند و بازیگری عالی از نقاط قوت آن است. فقط پایان‌بندی می‌توانست خلاقانه‌تر باشد.",
        "این اثر با داستان خنده‌دار و شخصیت‌های دوست‌داشتنی، لبخند را به لبتان می‌آورد. کارگردانی سبک و موسیقی متن شاد به جذابیت آن افزوده است. برخی شوخی‌ها ممکن است برای همه جذاب نباشند.",
        "فیلمی پر از خنده و لحظات شاد که شما را سرگرم خواهد کرد. بازیگران با زمان‌بندی عالی، کمدی را زنده کرده‌اند. فقط برخی موقعیت‌ها کمی کلیشه‌ای هستند.",
        "این کمدی با داستان بامزه و شوخی‌های هوشمندانه، شما را به وجد می‌آورد. کارگردانی خلاقانه و بازیگری پرانرژی دارد. فقط ریتم برخی صحنه‌ها می‌توانست بهتر باشد.",
        "داستانی خنده‌دار که با شخصیت‌های عجیب و غریب، شما را سرگرم می‌کند. دیالوگ‌های بامزه و کارگردانی خوب از نقاط قوت آن است. فقط برخی جوک‌ها ممکن است قدیمی به نظر برسند.",
        "این فیلم با کمدی سبک و داستان جذاب، اوقات خوشی برایتان رقم می‌زند. بازیگران با انرژی و موسیقی متن شاد، آن را خاص کرده‌اند. پایان‌بندی می‌توانست قوی‌تر باشد.",
        "کمدی‌ای که با شوخی‌های به‌جا و داستان سرگرم‌کننده، شما را می‌خنداند. کارگردانی پویا و بازیگری عالی دارد. فقط برخی لحظات ممکن است قابل‌پیش‌بینی باشند.",
        "این اثر با داستان خنده‌دار و شخصیت‌های بامزه، شما را شاد می‌کند. دیالوگ‌های هوشمندانه و ریتم خوب از نقاط قوت آن است. فقط برخی شوخی‌ها ممکن است برای همه مناسب نباشند.",
        "فیلمی که با کمدی سرزنده و داستان جذاب، شما را سرگرم می‌کند. بازیگران با شیمی عالی و کارگردانی خوب، آن را تماشایی کرده‌اند. فقط برخی صحنه‌ها می‌توانستند کوتاه‌تر باشند."
    ],
    'علمی-تخیلی': [
        "این فیلم با داستانی خلاقانه و جلوه‌های بصری خیره‌کننده، شما را به دنیایی دیگر می‌برد. کارگردانی هوشمندانه و موسیقی متن حماسی از نقاط قوت آن است. فقط برخی مفاهیم ممکن است پیچیده باشند.",
        "داستانی علمی-تخیلی که ذهن شما را به چالش می‌کشد. طراحی صحنه‌های آینده‌نگرانه و بازیگری قوی، آن را تماشایی کرده‌اند. فقط ریتم برخی صحنه‌ها می‌توانست سریع‌تر باشد.",
        "این اثر با ایده‌های نو و داستان جذاب، شما را شگفت‌زده می‌کند. جلوه‌های ویژه و کارگردانی خلاقانه از نقاط قوت آن است. فقط برخی توضیحات داستانی می‌توانستند واضح‌تر باشند.",
        "فیلمی که با داستانی تخیلی و جلوه‌های بصری فوق‌العاده، شما را مجذوب می‌کند. بازیگران با نقش‌آفرینی درخشان، داستان را زنده کرده‌اند. فقط پایان‌بندی می‌توانست قوی‌تر باشد.",
        "این داستان علمی-تخیلی با ایده‌های جسورانه، شما را به فکر فرو می‌برد. کارگردانی دقیق و موسیقی متن تأثیرگذار از نقاط قوت آن است. فقط برخی مفاهیم ممکن است برای همه قابل‌درک نباشند.",
        "فیلمی که با داستانی خلاق و جلوه‌های ویژه تماشایی، شما را سرگرم می‌کند. شخصیت‌پردازی قوی و کارگردانی خوب دارد. فقط برخی پیچش‌های داستانی می‌توانستند بهتر باشند.",
        "این اثر با داستانی آینده‌نگرانه و طراحی صحنه‌های خیره‌کننده، شما را به وجد می‌آورد. بازیگری عالی و موسیقی متن حماسی از نقاط قوت آن است. فقط ریتم برخی بخش‌ها می‌توانست بهتر باشد.",
        "داستانی علمی-تخیلی که با ایده‌های نو، شما را شگفت‌زده می‌کند. کارگردانی خلاقانه و جلوه‌های بصری فوق‌العاده دارد. فقط برخی جزئیات داستانی می‌توانستند روشن‌تر باشند.",
        "این فیلم با داستانی تخیلی و بازیگری قوی، شما را به دنیایی جدید می‌برد. طراحی صحنه‌های آینده‌نگرانه و موسیقی متن عالی از نقاط قوت آن است. فقط پایان‌بندی می‌توانست خلاقانه‌تر باشد.",
        "فیلمی که با داستانی جسورانه و جلوه‌های بصری تماشایی، شما را مجذوب می‌کند. کارگردانی هوشمندانه و بازیگری عالی دارد. فقط برخی مفاهیم ممکن است پیچیده به نظر برسند."
    ]
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
        return None
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

def get_fallback_by_genre(options, genres):
    """انتخاب فال‌بک بر اساس ژانر"""
    for genre in genres:
        if genre in options:
            available = [opt for opt in options[genre] if opt not in previous_comments and opt not in previous_plots]
            if available:
                return random.choice(available)
    available = [opt for genre in options for opt in options[genre] if opt not in previous_comments and opt not in previous_plots]
    return random.choice(available) if available else options[list(options.keys())[0]][0]

async def get_movie_info(title):
    """دریافت اطلاعات فیلم از TMDB با فیلترهای دقیق"""
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
            
            search_url_fa = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={encoded_title}&language=fa-IR"
            async with session.get(search_url_fa) as tmdb_response_fa:
                tmdb_data_fa = await tmdb_response_fa.json()
                tmdb_plot = tmdb_data_fa['results'][0].get('overview', '') if tmdb_data_fa.get('results') else ''
                tmdb_year = tmdb_data_fa['results'][0].get('release_date', 'N/A')[:4] if tmdb_data_fa.get('results') else 'N/A'
            
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
    """تولید تحلیل با Gemini یا Open AI"""
    global gemini_available, openai_available
    logger.info("تولید تحلیل...")
    
    # تلاش با Gemini
    if gemini_available:
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
            except google_exceptions.ResourceExhausted as e:
                logger.error(f"خطا: توکن Gemini تمام شده است: {str(e)}")
                gemini_available = False
                await send_admin_alert(None, "❌ توکن Gemini تمام شده است. تلاش با Open AI...")
            except Exception as e:
                logger.error(f"خطا در Gemini API (تلاش {attempt + 1}): {str(e)}")
    
    # تلاش با Open AI
    if openai_available and not gemini_available:
        try:
            response = await openai.ChatCompletion.acreate(
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
            if (len(sentences) >= 3 and is_farsi(text) and
                text not in previous_comments and len(text.split()) > 15):
                previous_comments.append(text)
                if len(previous_comments) > 10:
                    previous_comments.pop(0)
                return '. '.join(sentences[:3]) + '.'
            logger.warning(f"تحلیل Open AI نامعتبر: {text}")
        except openai.error.RateLimitError as e:
            logger.error(f"خطا: توکن Open AI تمام شده است: {str(e)}")
            openai_available = False
            await send_admin_alert(None, "❌ توکن Open AI تمام شده است. هیچ تحلیلگر دیگری در دسترس نیست.")
            return None
        except Exception as e:
            logger.error(f"خطا در Open AI API: {str(e)}")
    
    # فال‌بک نهایی
    if not gemini_available and not openai_available:
        logger.warning("هیچ تحلیلگری در دسترس نیست، استفاده از فال‌بک")
        comment = get_fallback_by_genre(FALLBACK_COMMENTS, genres)
        previous_comments.append(comment)
        if len(previous_comments) > 10:
            previous_comments.pop(0)
        return comment
    return None

async def send_admin_alert(context: ContextTypes.DEFAULT_TYPE, message: str):
    """ارسال هشدار به ادمین"""
    try:
        if context:
            await context.bot.send_message(ADMIN_ID, message)
        else:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                payload = {
                    "chat_id": ADMIN_ID,
                    "text": message
                }
                async with session.post(url, json=payload) as response:
                    result = await response.json()
                    if not result.get('ok'):
                        logger.error(f"خطا در ارسال هشدار به ادمین: {result}")
    except Exception as e:
        logger.error(f"خطا در ارسال هشدار به ادمین: {str(e)}")

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
        await send_admin_alert(context, "❌ خطا در آپدیت خودکار کش")

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
            comment = await generate_comment(movie_info['genres'])
            if not comment and not gemini_available and not openai_available:
                logger.error("تحلیل در دسترس نیست (توکن Gemini و Open AI تمام شده)")
                return None
            
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
    """ساخت منوی اصلی با دکمه‌های افقی"""
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
    version_info = "نسخه کد: 2025-04-18-v5 (فیکس دکمه‌ها با هندلرهای جدا، دکمه فعال/غیرفعال)"
    await update.message.reply_text(
        f"🤖 منوی ادمین\n{version_info}",
        reply_markup=get_main_menu()
    )

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دیباگ ساختار آپدیت"""
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
    """بازگشت به منوی اصلی"""
    query = update.callback_query
    logger.info("دکمه back_to_main")
    await query.answer()
    try:
        await query.message.edit_text("🤖 منوی ادمین", reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"خطا در back_to_main: {str(e)}")
        await query.message.edit_text(f"❌ خطا: {str(e)}", reply_markup=get_main_menu())

async def tests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی تست‌ها"""
    query = update.callback_query
    logger.info("دکمه tests_menu")
    await query.answer()
    try:
        await query.message.edit_text("🛠 منوی تست‌ها", reply_markup=get_tests_menu())
    except Exception as e:
        logger.error(f"خطا در tests_menu: {str(e)}")
        await query.message.edit_text(f"❌ خطا: {str(e)}", reply_markup=get_main_menu())

async def fetch_movies_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آپدیت دستی کش فیلم‌ها"""
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
    """ارسال پست دستی"""
    query = update.callback_query
    logger.info("دکمه post_now")
    await query.answer()
    msg = await query.message.edit_text("در حال آماده‌سازی پست...")
    try:
        if not bot_enabled:
            logger.error("ارسال پست کنسل شد: ربات غیرفعال است")
            await msg.edit_text("❌ ارسال پست کنسل شد: ربات غیرفعال است", reply_markup=get_main_menu())
            return
        if not gemini_available and not openai_available:
            logger.error("ارسال پست کنسل شد: توکن Gemini و Open AI تمام شده")
            await msg.edit_text("❌ ارسال پست کنسل شد: توکن Gemini و Open AI تمام شده", reply_markup=get_main_menu())
            await send_admin_alert(context, "❌ توکن Gemini و Open AI تمام شده است. لطفاً توکن جدید تنظیم کنید.")
            return
        
        movie = await get_random_movie()
        if not movie:
            logger.error("هیچ فیلمی انتخاب نشد (احتمالاً به دلیل اتمام توکن‌ها)")
            await msg.edit_text("❌ خطا در یافتن فیلم: توکن Gemini و Open AI ممکن است تمام شده باشند", reply_markup=get_main_menu())
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
    """تست سرویس‌های TMDB، JobQueue، Gemini و Open AI"""
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
        comment = await generate_comment(['درام'])
        results.append("✅ Gemini/Open AI اوکی" if comment else f"❌ Gemini/Open AI خطا: {'توکن تمام شده' if not gemini_available and not openai_available else 'مشکل ناشناخته'}")
    except Exception as e:
        results.append(f"❌ Gemini/Open AI خطا: {str(e)}")
    
    await msg.edit_text("\n".join(results), reply_markup=get_tests_menu())

async def test_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تست دسترسی به کانال"""
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
    """بررسی بازدید کانال بدون پیام تستی"""
    query = update.callback_query
    logger.info("دکمه stats")
    await query.answer()
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

async def show_movies_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست فیلم‌های کش‌شده"""
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
    """شروع اضافه کردن فیلم"""
    query = update.callback_query
    logger.info("دکمه add_movie")
    await query.answer()
    await query.message.edit_text("لطفاً نام فیلم را وارد کنید:")
    return ADD_MOVIE_TITLE

async def toggle_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر وضعیت فعال/غیرفعال ربات"""
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

async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    """ارسال پست خودکار"""
    logger.info("شروع پست خودکار...")
    try:
        if not bot_enabled:
            logger.info("پست خودکار کنسل شد: ربات غیرفعال است")
            return
        if not gemini_available and not openai_available:
            logger.error("پست خودکار کنسل شد: توکن Gemini و Open AI تمام شده")
            await send_admin_alert(context, "❌ پست خودکار کنسل شد: توکن Gemini و Open AI تمام شده است.")
            return
        
        movie = await get_random_movie()
        if not movie:
            logger.error("هیچ فیلمی انتخاب نشد (احتمالاً به دلیل اتمام توکن‌ها)")
            await send_admin_alert(context, "❌ خطا: فیلم برای پست خودکار یافت نشد (توکن Gemini و Open AI ممکن است تمام شده باشند)")
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
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("resetwebhook", reset_webhook))
    
    # هندلرهای جداگانه برای دکمه‌ها
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
    """زمان‌بندی جایگزین برای پست و آپدیت کش"""
    logger.info("اجرای زمان‌بندی جایگزین...")
    while True:
        await auto_post(context)
        await asyncio.sleep(600)
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
