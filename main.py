
import nest_asyncio
import asyncio
import logging
import os
import requests
import xml.etree.ElementTree as ET
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot, InputMediaPhoto
from telegram.constants import ParseMode
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
import uuid
from datetime import time
import pytz

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_log.txt'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "487591931"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@myttoy66")
YML_URL = os.getenv("YML_URL")

keyboard = [
    [InlineKeyboardButton("▶️ Следующий пост", callback_data="next")],
    [InlineKeyboardButton("⏸ Пауза", callback_data="pause"), InlineKeyboardButton("✅ Возобновить", callback_data="resume")],
    [InlineKeyboardButton("📋 Очередь постов", callback_data="queue")],
    [InlineKeyboardButton("📨 Написать сообщение", callback_data="broadcast")],
    [InlineKeyboardButton("📄 Лог", callback_data="log")],
    [InlineKeyboardButton("ℹ️ Статус", callback_data="status")],
    [InlineKeyboardButton("⏭ Пропустить товар", callback_data="skip")],
]
menu = InlineKeyboardMarkup(keyboard)

product_cache = []
product_queue = product_cache
paused = False
waiting_for_broadcast = False

def add_to_cache(product):
    if product["id"] not in [p["id"] for p in product_cache]:
        product_cache.append(product)

def get_next_product():
    if product_cache:
        return product_cache.pop(0)
    return None

def fetch_products_from_yml():
    try:
        response = requests.get(YML_URL)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            products = []
            for offer in root.findall(".//offer"):
                price = int(float(offer.findtext("price", "0")))
                picture = offer.findtext("picture")
                name = offer.findtext("name")
                description = offer.findtext("description", "")
                url = offer.findtext("url")
                category = offer.findtext("categoryId")
                vendor_code = offer.get("id")

                if not picture or price < 300:
                    continue

                products.append({
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "description": description,
                    "price": price,
                    "picture": picture,
                    "url": url,
                    "category": category,
                    "vendor_code": vendor_code
                })
            return products
    except Exception as e:
        logger.error(f"Ошибка при загрузке YML: {e}")
    return []

def generate_description_giga(name, description=""):
    try:
        headers = {
            "Authorization": f"Basic {os.getenv('GIGACHAT_API_KEY')}",
            "Content-Type": "application/json"
        }
        prompt = f"Сделай короткое продающее описание для товара: {name}. {description}"
        payload = {
            "model": "GigaChat-Pro",
            "messages": [{"role": "user", "content": prompt}]
        }
        response = requests.post(
            "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            headers=headers,
            json=payload
        )
        if response.status_code == 200:
            reply = response.json()
            return reply["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Ошибка при генерации описания: {e}")
    return "Отличный выбор! Подходит для любого случая."

async def post_next_product():
    product = get_next_product()
    if product:
        try:
            bot = Bot(token=BOT_TOKEN)
            caption = f"<b>{product['name']}</b>

"
            description = generate_description_giga(product['name'], product.get('description', ''))
            caption += f"{description}

<b>Цена: {product['price']} ₽</b>"
            url_button = InlineKeyboardButton("Купить", url=product['url'])
            markup = InlineKeyboardMarkup([[url_button]])

            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=product['picture'],
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=markup
            )
            logger.info(f"Товар отправлен: {product['name']}")
        except Exception as e:
            logger.error(f"Ошибка при отправке товара: {e}")

async def scheduled_post():
    if not paused and product_queue:
        await post_next_product()

async def main():
    global bot
    bot = Bot(token=BOT_TOKEN)
    dp = ApplicationBuilder().token(BOT_TOKEN).build()

    dp.add_handler(CallbackQueryHandler(callback_next, pattern="next"))
    dp.add_handler(CallbackQueryHandler(callback_pause, pattern="pause"))
    dp.add_handler(CallbackQueryHandler(callback_resume, pattern="resume"))
    dp.add_handler(CallbackQueryHandler(callback_queue, pattern="queue"))
    dp.add_handler(CallbackQueryHandler(callback_broadcast, pattern="broadcast"))
    dp.add_handler(CallbackQueryHandler(callback_log, pattern="log"))
    dp.add_handler(CallbackQueryHandler(callback_status, pattern="status"))
    dp.add_handler(CallbackQueryHandler(callback_skip, pattern="skip"))

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(scheduled_post, CronTrigger(hour=12, minute=0))
    scheduler.start()

    logging.info("Бот запущен")
    await dp.run_polling()

async def callback_next(update, context):
    await update.callback_query.answer()
    await post_next_product()

async def callback_pause(update, context):
    global paused
    paused = True
    await update.callback_query.answer("Публикация приостановлена.")

async def callback_resume(update, context):
    global paused
    paused = False
    await update.callback_query.answer("Публикация возобновлена.")

async def callback_queue(update, context):
    await update.callback_query.answer()
    queue_preview = "
".join([f"{idx+1}. {p['name']}" for idx, p in enumerate(product_queue[:10])])
    text = queue_preview if queue_preview else "Очередь пуста."
    await bot.send_message(update.effective_user.id, f"<b>Текущая очередь:</b>
{text}", parse_mode=ParseMode.HTML)

async def callback_broadcast(update, context):
    await update.callback_query.answer()
    await bot.send_message(update.effective_user.id, "Отправьте сообщение для рассылки (можно с фото и подписью):")

async def callback_log(update, context):
    await update.callback_query.answer()
    if os.path.exists('bot.log'):
        with open('bot.log', 'r', encoding='utf-8') as f:
            log_text = f.readlines()[-20:]
        await bot.send_message(update.effective_user.id, "<b>Лог:</b>
" + "".join(log_text), parse_mode=ParseMode.HTML)
    else:
        await bot.send_message(update.effective_user.id, "Лог-файл не найден.")

async def callback_status(update, context):
    await update.callback_query.answer()
    status = "Пауза" if paused else "Активен"
    await bot.send_message(update.effective_user.id, f"<b>Статус:</b> {status}", parse_mode=ParseMode.HTML)

async def callback_skip(update, context):
    await update.callback_query.answer("Товар пропущен.")
    if product_queue:
        product_queue.pop(0)

if __name__ == "__main__":
    try:
        nest_asyncio.apply()
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен вручную")
    except Exception as e:
        logging.exception(f"Произошла критическая ошибка: {e}")
