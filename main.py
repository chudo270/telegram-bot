import os
import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

# Логирование
logging.basicConfig(level=logging.INFO)

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Например: -1001234567890
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # ID админа Telegram
DATA_URL = os.getenv("DATA_URL")  # URL YML или API

# Фильтрация
MIN_PRICE = int(os.getenv("MIN_PRICE", "300"))

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Память для кеша
posted_products = set()
is_paused = False

async def fetch_products():
    async with aiohttp.ClientSession() as session:
        async with session.get(DATA_URL) as response:
            if response.status != 200:
                raise Exception(f"Ошибка загрузки данных: {response.status}")
            data = await response.json()

            # Примерная структура: [{"name": "...", "price": "...", "photo": "..."}]
            products = []
            for product in data:
                price = str(product.get("price", "0")).replace("₽", "").replace(",", ".")
                if price:
                    try:
                        price_value = float(price)
                        if price_value < MIN_PRICE:
                            continue
                        product["price"] = f"{int(price_value)} руб."
                    except ValueError:
                        continue
                else:
                    continue

                if not product.get("photo") or not product.get("description"):
                    continue

                products.append(product)

            return products

def generate_post(product):
    text = f"{product['name']}\n\n"
    if product.get("category"):
        text += f"Категория: {product['category']}\n"
    if product.get("article"):
        text += f"Артикул: {product['article']}\n"
    if product.get("price"):
        text += f"Цена: {product['price']}\n"
    if product.get("description"):
        text += f"\n{product['description']}"
    else:
        text += "\nОписание скоро появится!"

    keyboard = InlineKeyboardMarkup()
    if product.get("url"):
        keyboard.add(InlineKeyboardButton("Подробнее", url=product["url"]))
    return text, keyboard

async def publish_next_product():
    global posted_products, is_paused

    if is_paused:
        return

    try:
        products = await fetch_products()
        for product in products:
            product_id = product.get("id") or product.get("article") or product.get("name")
            if product_id in posted_products:
                continue

            text, keyboard = generate_post(product)
            photo = product.get("photo")

            if photo:
                await bot.send_photo(CHANNEL_ID, photo=photo, caption=text, reply_markup=keyboard)
            else:
                await bot.send_message(CHANNEL_ID, text, reply_markup=keyboard)

            posted_products.add(product_id)
            break

    except Exception as e:
        logging.error(f"Ошибка публикации: {e}")
        await bot.send_message(ADMIN_ID, f"Ошибка публикации:\n{e}")

# Команды для управления ботом
@dp.message_handler(commands=["start", "help"])
async def cmd_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply("Доступные команды:\n/next — следующий товар\n/pause — пауза\n/resume — продолжить\n/status — статус\n/log — лог")

@dp.message_handler(commands=["next"])
async def cmd_next(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await publish_next_product()
        await message.reply("Опубликован следующий товар.")

@dp.message_handler(commands=["pause"])
async def cmd_pause(message: types.Message):
    global is_paused
    if message.from_user.id == ADMIN_ID:
        is_paused = True
        await message.reply("Публикация приостановлена.")

@dp.message_handler(commands=["resume"])
async def cmd_resume(message: types.Message):
    global is_paused
    if message.from_user.id == ADMIN_ID:
        is_paused = False
        await message.reply("Публикация возобновлена.")

@dp.message_handler(commands=["status"])
async def cmd_status(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        status = "на паузе" if is_paused else "активен"
        await message.reply(f"Бот сейчас: {status}. Опубликовано товаров: {len(posted_products)}")

@dp.message_handler(commands=["log"])
async def cmd_log(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.reply("Пока логов нет или они в stdout.")

# Планировщик публикации
scheduler = AsyncIOScheduler()
scheduler.add_job(publish_next_product, "cron", hour=12, minute=0)  # каждый день в 12:00

async def on_startup(dp):
    scheduler.start()
    await bot.send_message(ADMIN_ID, f"Бот запущен: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)
