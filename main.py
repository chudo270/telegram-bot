import logging
import requests
import random
import time
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.constants import ParseMode
from telegram import Update


# --- НАСТРОЙКИ ---
TOKEN = '7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0'
CHANNEL_ID = '@Botrepostai_bot'
ADMIN_ID = 487591931
MAIN_URL = 'https://mytoy66.ru/group?type=latest'
RESERVE_URL = 'https://mytoy66.ru/integration?int=avito&name=avitoo'
POST_HOUR = 12
POST_MINUTE = 0

# --- ЛОГИ ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
pause = False
product_cache = []
last_posted = set()

# --- ПОЛУЧЕНИЕ ТОВАРОВ ---
def fetch_products():
    try:
        r = requests.get(MAIN_URL, timeout=10)
        if r.status_code == 200 and 'products' in r.json():
            return r.json()['products']
    except:
        pass
    try:
        r = requests.get(RESERVE_URL, timeout=10)
        if r.status_code == 200 and '<offer>' in r.text:
            return parse_yml(r.text)
    except:
        pass
    return []

def parse_yml(yml):
    from xml.etree import ElementTree
    root = ElementTree.fromstring(yml)
    offers = []
    for offer in root.findall(".//offer"):
        name = offer.findtext("name")
        price = offer.findtext("price")
        pic = offer.findtext("picture")
        desc = offer.findtext("description") or ""
        if name and pic and float(price or 0) >= 300:
            offers.append({
                'name': name.strip(),
                'price': price.strip(),
                'image': pic.strip(),
                'description': desc.strip()
            })
    return offers

# --- ГЕНЕРАЦИЯ ОПИСАНИЯ ---
def generate_description(product):
    if product.get('description'):
        return product['description']
    return f"{product['name']} по суперцене {product['price']} ₽. Успей купить!"

# --- ПУБЛИКАЦИЯ ТОВАРА ---
def post_product(bot: Bot):
    global product_cache
    if not product_cache:
        product_cache = fetch_products()
        random.shuffle(product_cache)

    while product_cache:
        product = product_cache.pop()
        if product.get('image') and float(product.get('price', 0)) >= 300:
            uid = product['name'] + product['image']
            if uid in last_posted:
                continue
            last_posted.add(uid)
            text = f"<b>{product['name']}</b>\nЦена: {product['price']} ₽\n\n{generate_description(product)}"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Купить", url=product['image'])]])
            bot.send_photo(chat_id=CHANNEL_ID, photo=product['image'], caption=text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            logger.info(f"Posted: {product['name']}")
            break

# --- КОМАНДЫ АДМИНА ---
def is_admin(user_id): return user_id == ADMIN_ID

def start(update: Update, context: CallbackContext): update.message.reply_text("Бот работает.")
def status(update: Update, context: CallbackContext): update.message.reply_text("Пауза: " + str(pause))
def pause_cmd(update: Update, context: CallbackContext):
    global pause
    if is_admin(update.effective_user.id):
        pause = True
        update.message.reply_text("Пауза включена.")

def resume(update: Update, context: CallbackContext):
    global pause
    if is_admin(update.effective_user.id):
        pause = False
        update.message.reply_text("Пауза отключена.")

def next_post(update: Update, context: CallbackContext):
    if is_admin(update.effective_user.id):
        post_product(context.bot)
        update.message.reply_text("Опубликовано.")

def log(update: Update, context: CallbackContext):
    if is_admin(update.effective_user.id):
        update.message.reply_text(f"Кэш: {len(product_cache)} | Последние: {len(last_posted)}")

# --- ЕЖЕДНЕВНЫЙ ПОСТИНГ ---
def scheduler(context: CallbackContext):
    if not pause:
        post_product(context.bot)

# --- ОСНОВНОЙ ЗАПУСК ---
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("pause", pause_cmd))
    dp.add_handler(CommandHandler("resume", resume))
    dp.add_handler(CommandHandler("next", next_post))
    dp.add_handler(CommandHandler("log", log))

    job_queue = updater.job_queue
    job_queue.run_daily(scheduler, time=time(hour=POST_HOUR, minute=POST_MINUTE))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
