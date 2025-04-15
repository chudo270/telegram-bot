import os
import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.utils.markdown import hbold
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

# Логирование
logging.basicConfig(level=logging.INFO)

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATA_URL = os.getenv("DATA_URL")
MIN_PRICE = int(os.getenv("MIN_PRICE", "300"))

# Инициализация
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())

# Внутренняя память
posted_products = set()
is_paused = False

async def fetch_products():
    async with aiohttp.ClientSession() as session:
        async with session.get(DATA_URL) as response:
            if response.status != 200:
                raise Exception(f"Ошибка загрузки данных: {response.status}")
            data = await response.json()

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
    text = f"{hbold(product['name'])}\n\n"
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

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подробнее", url=product["url"])] if product.get("url") else []
        ]
    )
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

# Команды
@dp.message(Command(commands=["start", "help"]))
async def cmd_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Доступные команды:\n/next — следующий товар\n/pause — пауза\n/resume — продолжить\n/status — статус\n/log — лог")

@dp.message(Command(commands=["next"]))
async def cmd_next(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await publish_next_product()
        await message.answer("Опубликован следующий товар.")

@dp.message(Command(commands=["pause"]))
async def cmd_pause(message: types.Message):
    global is_paused
    if message.from_user.id == ADMIN_ID:
        is_paused = True
        await message.answer("Публикация приостановлена.")

@dp.message(Command(commands=["resume"]))
async def cmd_resume(message: types.Message):
    global is_paused
    if message.from_user.id == ADMIN_ID:
        is_paused = False
        await message.answer("Публикация возобновлена.")

@dp.message(Command(commands=["status"]))
async def cmd_status(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        status = "на паузе" if is_paused else "активен"
        await message.answer(f"Бот сейчас: {status}. Опубликовано товаров: {len(posted_products)}")

@dp.message(Command(commands=["log"]))
async def cmd_log(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Пока логов нет или они в stdout.")

# Планировщик
scheduler = AsyncIOScheduler()
scheduler.add_job(publish_next_product, "cron", hour=12, minute=0)

async def main():
    scheduler.start()
    await bot.send_message(ADMIN_ID, f"Бот запущен: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
