import os
import asyncio
import logging
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# Конфигурация
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "@mytoy66"
ADMIN_ID = 487591931

YML_URL = "https://mytoy66.ru/integration?int=avito&name=avitoo"

# Глобальные переменные
awaiting_broadcast = False
paused = False
products_cache = []
product_index = 0

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename="bot.log",
    filemode="a"
)

# Загрузка товаров
async def fetch_products():
    global products_cache
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(YML_URL) as response:
                text = await response.text()
                # Пока пример одного товара, здесь парсинг YML при необходимости
                products_cache = [{"name": "Пример", "price": 500, "description": "Описание товара", "picture": "https://via.placeholder.com/300"}]
                logging.info("Загружено товаров: %d", len(products_cache))
    except Exception as e:
        logging.error("Ошибка загрузки товаров: %s", str(e))
        products_cache = []

# Отправка товара
async def send_product(context: ContextTypes.DEFAULT_TYPE, product: dict):
    try:
        message = f"<b>{product['name']}</b>\nЦена: {product['price']}₽\n\n{product['description']}"
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=product['picture'],
            caption=message,
            parse_mode="HTML"
        )
        logging.info("Отправлен товар: %s", product['name'])
    except Exception as e:
        logging.error("Ошибка при отправке товара: %s", str(e))

# Публикация следующего товара
async def post_product(context: ContextTypes.DEFAULT_TYPE = None):
    global product_index, paused

    if paused or not products_cache:
        logging.info("Публикация приостановлена или нет товаров.")
        return

    if product_index >= len(products_cache):
        product_index = 0

    product = products_cache[product_index]
    await send_product(context, product)
    product_index += 1

# Команды Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    keyboard = [
        [InlineKeyboardButton("▶️ Следующий пост", callback_data="next")],
        [InlineKeyboardButton("⏸ Пауза", callback_data="pause"), InlineKeyboardButton("✅ Возобновить", callback_data="resume")],
        [InlineKeyboardButton("📋 Очередь постов", callback_data="queue")],
        [InlineKeyboardButton("📨 Написать сообщение", callback_data="broadcast")],
        [InlineKeyboardButton("📄 Лог", callback_data="log")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Меню управления:", reply_markup=reply_markup)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global awaiting_broadcast, paused

    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text

    if text == "📨 Написать сообщение":
        awaiting_broadcast = True
        await update.message.reply_text("Введите сообщение для канала.")
    elif text == "📋 Очередь постов":
        await update.message.reply_text(f"Осталось товаров: {len(products_cache) - product_index}")
    elif text == "▶️ Следующий пост":
        await post_product(context)
    elif text == "⏸ Пауза":
        paused = True
        await update.message.reply_text("Публикации приостановлены.")
    elif text == "✅ Возобновить":
        paused = False
        await update.message.reply_text("Публикации возобновлены.")
    elif text == "📄 Лог":
        if os.path.exists("bot.log"):
            with open("bot.log", "rb") as f:
                await context.bot.send_document(chat_id=ADMIN_ID, document=f, filename="bot.log")
        else:
            await update.message.reply_text("Файл лога не найден.")
    elif awaiting_broadcast:
        awaiting_broadcast = False
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text)
        await update.message.reply_text("Сообщение отправлено.")
    else:
        await update.message.reply_text("Неизвестная команда.")

# Плановая отправка
async def schedule_daily_post():
    await post_product()

# Главная функция
async def main():
    await fetch_products()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

    # Планировщик
    scheduler = AsyncIOScheduler()
    scheduler.add_job(schedule_daily_post, "cron", hour=12, minute=0)
    scheduler.add_job(post_product, "interval", minutes=60)
    scheduler.start()

    await application.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
