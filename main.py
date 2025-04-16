import nest_asyncio
import asyncio
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
def send_product(bot: Bot, chat_id: int, product: dict):
    try:
        caption = f"<b>{product['name']}</b>\n\n"
        description = generate_description_giga(product['name'], product.get('description', ''))
        caption += f"{description}\n\n<b>Цена: {product['price']} ₽</b>"
        url_button = InlineKeyboardButton("Купить", url=product['url'])
        markup = InlineKeyboardMarkup([[url_button]])

        bot.send_photo(
            chat_id=chat_id,
            photo=product['picture'],
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
        logger.info(f"Товар отправлен: {product['name']}")
    except Exception as e:
        logger.error(f"Ошибка при отправке товара: {e}")
@dp.callback_query_handler(lambda c: c.data == 'next')
async def callback_next(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await post_next_product()

@dp.callback_query_handler(lambda c: c.data == 'pause')
async def callback_pause(callback_query: types.CallbackQuery):
    global paused
    paused = True
    await bot.answer_callback_query(callback_query.id, text="Публикация приостановлена.")

@dp.callback_query_handler(lambda c: c.data == 'resume')
async def callback_resume(callback_query: types.CallbackQuery):
    global paused
    paused = False
    await bot.answer_callback_query(callback_query.id, text="Публикация возобновлена.")

@dp.callback_query_handler(lambda c: c.data == 'queue')
async def callback_queue(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    queue_preview = "\n".join([f"{idx+1}. {p['name']}" for idx, p in enumerate(product_queue[:10])])
    text = queue_preview if queue_preview else "Очередь пуста."
    await bot.send_message(callback_query.from_user.id, f"<b>Текущая очередь:</b>\n{text}", parse_mode=ParseMode.HTML)

@dp.callback_query_handler(lambda c: c.data == 'broadcast')
async def callback_broadcast(callback_query: types.CallbackQuery):
    global waiting_for_broadcast
    waiting_for_broadcast = True
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Отправьте сообщение для рассылки (можно с фото и подписью):")

    # Здесь должно быть логическое продолжение в виде FSM или глобального флага ожидания текста

@dp.callback_query_handler(lambda c: c.data == 'log')
async def callback_log(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    if os.path.exists('bot.log'):
        with open('bot.log', 'r', encoding='utf-8') as f:
            log_text = f.readlines()[-20:]  # последние 20 строк
        await bot.send_message(callback_query.from_user.id, "<b>Лог:</b>\n" + "".join(log_text), parse_mode=ParseMode.HTML)
    else:
        await bot.send_message(callback_query.from_user.id, "Лог-файл не найден.")

@dp.callback_query_handler(lambda c: c.data == 'status')
async def callback_status(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    status = "Пауза" if paused else "Активен"
    await bot.send_message(callback_query.from_user.id, f"<b>Статус:</b> {status}", parse_mode=ParseMode.HTML)

@dp.callback_query_handler(lambda c: c.data == 'skip')
async def callback_skip(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="Товар пропущен.")
    if product_queue:
        product_queue.pop(0)
async def scheduled_post():
    if not paused and product_queue:
        await post_next_product()

async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(scheduled_post, CronTrigger(hour=12, minute=0))  # ежедневная публикация в 12:00 МСК
    scheduler.start()

    logging.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен вручную")
    except Exception as e:
        logging.exception(f"Произошла критическая ошибка: {e}")
