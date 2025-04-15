import logging
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from telegram import Update, InputMediaPhoto, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, time

TOKEN = "7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0"
ADMIN_ID = 487591931
CHANNEL_ID = "@myttoy66"
YML_URL = "https://mytoy66.ru/integration?int=avito&name=avitoo"

logging.basicConfig(level=logging.INFO)
scheduler = AsyncIOScheduler()
product_queue = []
paused = False
awaiting_broadcast = False

# --- Утилиты ---

async def fetch_url(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

def parse_yml_content(xml_text):
    products = []
    try:
        root = ET.fromstring(xml_text)
        for offer in root.findall('.//offer'):
            price = float(offer.find('price').text or 0)
            picture = offer.find('picture')
            if price < 300 or picture is None:
                continue
            name = offer.find('name').text or ''
            description = offer.find('description').text or ''
            url = offer.find('url').text or ''
            products.append({
                'name': name,
                'description': description,
                'price': price,
                'url': url,
                'picture': picture.text
            })
    except Exception as e:
        logging.error(f"YML parsing error: {e}")
    return products

def get_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("▶️ Следующий пост"), KeyboardButton("⏸ Пауза"), KeyboardButton("✅ Возобновить")],
            [KeyboardButton("🗂 Очередь постов"), KeyboardButton("📋 Лог"), KeyboardButton("✉️ Написать сообщение")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

# --- Команды и обработчики ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен.", reply_markup=get_keyboard())

async def post_product(context=None):
    try:
        if not product_queue:
            await fetch_products()

        if product_queue:
            product = product_queue.pop(0)
            await send_product(product)
        else:
            await bot.send_message(ADMIN_ID, "Очередь пуста, товаров нет для публикации.")
    except Exception as e:
        await bot.send_message(ADMIN_ID, f"Ошибка при публикации товара: {e}")


async def schedule_daily_post():
    xml = await fetch_url(YML_URL)
    global product_queue
    product_queue = parse_yml_content(xml)
    logging.info(f"Загружено товаров: {len(product_queue)}")

async def manual_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await post_product(context)

async def pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id == ADMIN_ID:
        paused = True
        await update.message.reply_text("Постинг приостановлен.")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id == ADMIN_ID:
        paused = False
        await update.message.reply_text("Постинг возобновлён.")

async def show_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("Ошибок нет. Все работает.")

async def show_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(f"В очереди {len(product_queue)} товаров.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global awaiting_broadcast
    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text
    if text == "✉️ Написать сообщение":
        awaiting_broadcast = True
        await update.message.reply_text("Введите сообщение для канала.")
    elif text == "📋 Лог":
        await show_log(update, context)
    elif text == "🗂 Очередь постов":
        await show_queue(update, context)
    elif text == "▶️ Следующий пост":
        await manual_post(update, context)
    elif text == "⏸ Пауза":
        await pause_bot(update, context)
    elif text == "✅ Возобновить":
        await resume_bot(update, context)
    elif awaiting_broadcast:
        awaiting_broadcast = False
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text)
        await update.message.reply_text("Сообщение отправлено в канал.")
    else:
        await update.message.reply_text("Неизвестная команда.")

# --- Запуск бота ---

async def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

    scheduler.add_job(schedule_daily_post, "cron", hour=12, minute=0)
    scheduler.add_job(post_product, "interval", minutes=60)
    scheduler.start()

    await schedule_daily_post()
    await application.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    import asyncio

    nest_asyncio.apply()  # <-- Позволяет запускать loop повторно
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
