import logging
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
from datetime import datetime

# Настройки
TOKEN = "7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0"
CHANNEL_ID = "@mytoy66_channel"  # Замени на свой канал
ADMIN_ID = 487591931
MAIN_SOURCE_URL = "https://mytoy66.ru/group?type=latest"
YML_URL = "https://mytoy66.ru/integration?int=avito&name=avitoo"
WRITING_MODE = {}

# Логгер
logging.basicConfig(level=logging.INFO)

# Генерация описания
def generate_description(title):
    return f"Превосходный товар: {title}. Отлично подойдёт для вас!"

# Получение товаров с HTML
def get_products_from_html():
    try:
        response = requests.get(MAIN_SOURCE_URL, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select(".product-block")

        products = []
        for item in items:
            name_tag = item.select_one(".product-name")
            price_tag = item.select_one(".price")
            image_tag = item.select_one("img")
            link_tag = item.select_one("a")

            name = name_tag.text.strip() if name_tag else ""
            price = price_tag.text.strip().replace("₽", "").replace(" ", "") if price_tag else ""
            price = int(price) if price.isdigit() else 0
            img = image_tag["src"] if image_tag and image_tag.get("src") else ""
            link = "https://mytoy66.ru" + link_tag["href"] if link_tag else ""
            description = generate_description(name)

            if name and price >= 300 and img:
                products.append({
                    "name": name,
                    "price": price,
                    "img": img,
                    "description": description,
                    "link": link
                })

        return products
    except Exception as e:
        logging.error(f"[{datetime.now()}] Ошибка при парсинге HTML: {e}")
        return []

# Публикация товара
async def post_product(context: ContextTypes.DEFAULT_TYPE):
    products = get_products_from_html()
    if not products:
        products = get_products_from_yml()

    if products:
        product = products[0]  # Можно сделать ротацию
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Купить", url=product["link"])]])
        caption = f"*{product['name']}*\n\n{product['description']}\n\nЦена: {product['price']}₽"
        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=product['img'], caption=caption, parse_mode='Markdown', reply_markup=keyboard)
    else:
        logging.info(f"[{datetime.now()}] Нет подходящих товаров")

# YML парсинг (резерв)
def get_products_from_yml():
    try:
        import xml.etree.ElementTree as ET
        response = requests.get(YML_URL, timeout=10)
        tree = ET.fromstring(response.content)
        products = []

        for offer in tree.findall(".//offer"):
            name = offer.find("name").text if offer.find("name") is not None else ""
            price = float(offer.find("price").text) if offer.find("price") is not None else 0
            img = offer.find("picture").text if offer.find("picture") is not None else ""
            desc = offer.find("description").text if offer.find("description") is not None else generate_description(name)
            link = offer.find("url").text if offer.find("url") is not None else ""

            if name and price >= 300 and img:
                products.append({
                    "name": name,
                    "price": price,
                    "img": img,
                    "description": desc,
                    "link": link
                })

        return products
    except Exception as e:
        logging.error(f"[{datetime.now()}] Ошибка при парсинге YML: {e}")
        return []

# Команда start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    keyboard = [
        [InlineKeyboardButton("▶️ Следующий товар", callback_data="next")],
        [InlineKeyboardButton("📝 Написать", callback_data="write")]
    ]
    await update.message.reply_text("Добро пожаловать, админ!", reply_markup=InlineKeyboardMarkup(keyboard))

# Обработка кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if user_id != ADMIN_ID:
        return

    if query.data == "next":
        await post_product(context)
    elif query.data == "write":
        WRITING_MODE[user_id] = True
        await query.message.reply_text("Напиши сообщение, и я отправлю его в канал.")

# Обработка текстов после "Написать"
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if WRITING_MODE.get(user_id):
        WRITING_MODE[user_id] = False
        await context.bot.send_message(chat_id=CHANNEL_ID, text=update.message.text)
        await update.message.reply_text("Сообщение отправлено в канал.")
    else:
        await update.message.reply_text("Используй кнопки для управления ботом.")

# Главная функция
async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.create_task(post_product(app.bot)), "cron", hour=12, minute=0)
    scheduler.start()

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
