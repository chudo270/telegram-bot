import logging
import os
import requests
import xml.etree.ElementTree as ET
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_log.txt'
)
logger = logging.getLogger(__name__)

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN", "7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0")
ADMIN_ID = 487591931
CHANNEL_ID = "@myttoy66"
YML_URL = "https://cdn.mysitemapgenerator.com/shareapi/yml/16046306746_514"

keyboard = [
    [InlineKeyboardButton("▶️ Следующий пост", callback_data="next")],
    [InlineKeyboardButton("⏸ Пауза", callback_data="pause"), InlineKeyboardButton("✅ Возобновить", callback_data="resume")],
    [InlineKeyboardButton("📋 Очередь постов", callback_data="queue")],
    [InlineKeyboardButton("📨 Написать сообщение", callback_data="broadcast")],
    [InlineKeyboardButton("📄 Лог", callback_data="log")],
]
menu = InlineKeyboardMarkup(keyboard)

def fetch_products_from_yml():
    try:
        response = requests.get(YML_URL)
        response.raise_for_status()
        tree = ET.fromstring(response.content)

        products = []
        for offer in tree.findall(".//offer"):
            name = offer.findtext("name")
            price = offer.findtext("price")
            picture = offer.findtext("picture")
            url = offer.findtext("url")
            description = offer.findtext("description") or ""

            if not picture or not price or float(price) < 300:
                continue

            products.append({
                "name": name,
                "price": float(price),
                "picture": picture,
                "url": url,
                "description": description
            })

        return products

    except Exception as e:
        logger.error(f"Ошибка загрузки YML: {e}")
        return []

async def send_product(context: ContextTypes.DEFAULT_TYPE):
    if context.bot_data.get("paused", False):
        return

    queue = context.bot_data.get("queue", [])
    index = context.bot_data.get("queue_index", 0)

    if not queue:
        await context.bot.send_message(chat_id=ADMIN_ID, text="Очередь пуста.")
        return

    if index >= len(queue):
        await context.bot.send_message(chat_id=ADMIN_ID, text="Больше нет товаров в очереди.")
        return

    product = queue[index]
    link = f"<a href=\"{product['url']}\">Открыть товар на сайте</a>" if product.get("url") else ""
    caption = f"<b>{product['name']}</b>\nЦена: {product['price']}₽\n\n{product['description']}\n\n{link}"

    await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=product['picture'],
        caption=caption,
        parse_mode='HTML'
    )

    context.bot_data["queue_index"] = index + 1
    logger.info(f"Опубликован товар: {product['name']}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Панель управления ботом", reply_markup=menu)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    query = update.callback_query
    await query.answer()

    try:
        await query.delete_message()
    except:
        pass

    if query.data == "next":
        await send_product(context)
        await context.bot.send_message(chat_id=ADMIN_ID, text="Следующий товар отправлен.", reply_markup=menu)

    elif query.data == "pause":
        context.bot_data["paused"] = True
        await context.bot.send_message(chat_id=ADMIN_ID, text="Публикации приостановлены.", reply_markup=menu)

    elif query.data == "resume":
        context.bot_data["paused"] = False
        await context.bot.send_message(chat_id=ADMIN_ID, text="Публикации возобновлены.", reply_markup=menu)

    elif query.data == "queue":
        queue = context.bot_data.get("queue", [])
        current = context.bot_data.get("queue_index", 0)
        total = len(queue)
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"Товаров в очереди: {total - current} из {total}", reply_markup=menu)

    elif query.data == "log":
        if os.path.exists("bot_log.txt"):
            with open("bot_log.txt", "r", encoding="utf-8") as f:
                log_content = f.read()[-4000:]
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"Лог:\n\n{log_content}", reply_markup=menu)
        else:
            await context.bot.send_message(chat_id=ADMIN_ID, text="Файл логов не найден.", reply_markup=menu)

    elif query.data == "broadcast":
        context.user_data["awaiting_broadcast"] = True
        await context.bot.send_message(chat_id=ADMIN_ID, text="Напиши сообщение, которое хочешь разослать в канал.", reply_markup=menu)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if context.user_data.get("awaiting_broadcast"):
        text = update.message.text
        context.user_data["awaiting_broadcast"] = False
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text)
        await update.message.reply_text("Сообщение отправлено в канал.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    products = fetch_products_from_yml()
    app.bot_data["queue"] = products
    app.bot_data["queue_index"] = 0
    app.bot_data["paused"] = False

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_product, CronTrigger(hour=12, minute=0, timezone="Europe/Moscow"), args=[app])
    scheduler.start()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

