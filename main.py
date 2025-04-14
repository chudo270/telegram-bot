import os
import time
import random
import logging
import asyncio
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", "69033573"))  # fallback на твой ID

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

published_ids = set()
paused = False

def get_products():
    try:
        response = requests.get("https://mytoy66.ru/integration?int=avito&name=avitoo")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"Ошибка при получении товаров: {e}")
        return []

def generate_post(product):
    text = f"{product['name']}\n\n"
    if product.get("category"):
        text += f"Категория: {product['category']}\n"
    if product.get("article"):
        text += f"Артикул: {product['article']}\n"
    if product.get("price"):
        text += f"Цена: {product['price']} руб.\n"
    if product.get("description"):
        text += f"\n{product['description']}"
    else:
        text += "\nОписание скоро появится!"

    keyboard = InlineKeyboardMarkup()
    if product.get("url"):
        keyboard.add(InlineKeyboardButton("Подробнее", url=product["url"]))
    return text, keyboard

async def publish_next():
    global published_ids
    products = get_products()
    random.shuffle(products)
    for product in products:
        if product.get("id") in published_ids:
            continue
        if not product.get("image") or not product.get("description"):
            continue
        if int(product.get("price", 0)) < 300:
            continue

        text, keyboard = generate_post(product)
        try:
            if product.get("image"):
                await bot.send_photo(CHANNEL_ID, photo=product["image"], caption=text, reply_markup=keyboard)
            else:
                await bot.send_message(CHANNEL_ID, text, reply_markup=keyboard)
            published_ids.add(product["id"])
            break
        except Exception as e:
            logging.error(f"Ошибка при публикации: {e}")

@dp.message_handler(commands=["start", "help"])
async def send_welcome(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply("Доступные команды:\n/next — опубликовать следующий товар\n/pause — пауза/возобновление\n/status — статус\n/log — лог")

@dp.message_handler(commands=["next"])
async def cmd_next(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await publish_next()
    await message.reply("Попробовал опубликовать следующий товар.")

@dp.message_handler(commands=["pause"])
async def cmd_pause(message: types.Message):
    global paused
    if message.from_user.id != ADMIN_ID:
        return
    paused = not paused
    status = "Пауза" if paused else "Возобновил публикации"
    await message.reply(status)

@dp.message_handler(commands=["status"])
async def cmd_status(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply(f"Статус: {'Пауза' if paused else 'Активен'}\nОпубликовано товаров: {len(published_ids)}")

@dp.message_handler(commands=["log"])
async def cmd_log(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply("Логирование включено. Ошибки пишутся в консоль.")

async def scheduler():
    while True:
        if not paused:
            now = time.localtime()
            if now.tm_hour == 12 and now.tm_min == 0:
                await publish_next()
                await asyncio.sleep(60)
        await asyncio.sleep(30)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler())
    executor.start_polling(dp, skip_updates=True)

    except Exception as e:
        print(f"Ошибка при получении товаров с сайта: {e}")
        return []

def fetch_yml_products():
    try:
        response = requests.get(FALLBACK_YML_URL)
        products = []
        root = ET.fromstring(response.content)
        for offer in root.findall(".//offer"):
            name = offer.find("name").text if offer.find("name") is not None else None
            price = offer.find("price").text if offer.find("price") is not None else None
            picture = offer.find("picture").text if offer.find("picture") is not None else None
            url = offer.find("url").text if offer.find("url") is not None else None

            if not name or not price or not picture or not url:
                continue

            try:
                price_val = int(float(price))
            except ValueError:
                continue

            if price_val < MIN_PRICE:
                continue

            products.append({
                "title": name,
                "price": price_val,
                "image": picture,
                "url": url
            })
        return products
    except Exception as e:
        print(f"Ошибка при получении товаров из YML: {e}")
        return []

def generate_caption(product):
    return f"{product['title']}"

Цена: {product['price']}₽
Ссылка: {product['url']}"

def publish_product():
    global used_products
    if paused:
        print("Бот на паузе, публикация отменена")
        return

    products = fetch_products()
    if not products:
        print("Основной сайт не дал товаров, используем YML")
        products = fetch_yml_products()

    products = [p for p in products if p["url"] not in used_products]

    if not products:
        print("Нет новых товаров для публикации")
        return

    product = random.choice(products)
    used_products.append(product["url"])

    try:
        bot.send_photo(CHANNEL_ID, product["image"], caption=generate_caption(product))
        print(f"Опубликован товар: {product['title']}")
    except Exception as e:
        print(f"Ошибка при публикации товара: {e}")

@bot.message_handler(commands=["next", "pause", "resume", "status", "log"])
def handle_commands(message):
    global paused
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "У вас нет доступа")
        return

    cmd = message.text.strip().lower()
    if cmd == "/next":
        publish_product()
        bot.reply_to(message, "Товар опубликован")
    elif cmd == "/pause":
        paused = True
        bot.reply_to(message, "Пауза активирована")
    elif cmd == "/resume":
        paused = False
        bot.reply_to(message, "Пауза отключена")
    elif cmd == "/status":
        status = "на паузе" if paused else "активен"
        bot.reply_to(message, f"Статус: {status}")
    elif cmd == "/log":
        bot.reply_to(message, f"Использовано товаров: {len(used_products)}")

def scheduler_loop():
    schedule.every().day.at(f"{POST_HOUR:02d}:00").do(publish_product)
    while True:
        schedule.run_pending()
        time.sleep(60)

import threading
threading.Thread(target=scheduler_loop).start()

print("Бот запущен. Ожидаем публикации...")
bot.infinity_polling()
