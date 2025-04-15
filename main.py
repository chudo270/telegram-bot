import logging
import requests
import random
import time
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.constants import ParseMode
import asyncio
import datetime

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
        if r.status_code == 200 and 'products' in r.json():
            return r.json()['products']
    except:
        pass
    return []

# --- ПОСТИНГ ---
async def post_product(application):
    global product_cache, last_posted
    while True:
        now = datetime.datetime.now()
        if now.hour == POST_HOUR and now.minute == POST_MINUTE and not pause:
            if not product_cache:
                product_cache = fetch_products()

            for product in product_cache:
                if product['id'] in last_posted:
                    continue
                if product.get('price', 0) < 300 or not product.get('images') or not product.get('name'):
                    continue

                desc = product.get('description') or f"{product['name']}\nЦена: {product['price']}₽"
                image_url = product['images'][0]
                caption = f"<b>{product['name']}</b>\n{desc}\n\nЦена: {product['price']}₽"

                await application.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
                last_posted.add(product['id'])
                break
        await asyncio.sleep(60)

# --- КОМАНДЫ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("Бот работает. Используй /pause, /resume, /next, /status, /log")

async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pause
    if update.effective_user.id == ADMIN_ID:
        pause = True
        await update.message.reply_text("Пауза включена")

async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pause
    if update.effective_user.id == ADMIN_ID:
        pause = False
        await update.message.reply_text("Пауза снята")

async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        global product_cache
        if not product_cache:
            product_cache = fetch_products()
        await post_product(context.application)

# --- ЗАПУСК ---
async def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("next", next_command))

    # Запускаем фоновую задачу
    application.job_queue.run_repeating(lambda ctx: asyncio.create_task(post_product(application)), interval=60)

    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
