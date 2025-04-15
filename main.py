import logging
import datetime
import asyncio
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,
    filters, CallbackQueryHandler
)

BOT_TOKEN = '7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0'
ADMIN_ID = 487591931

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

posting_paused = False
current_product_index = 0
products_cache = []

# --- Парсинг сайта ---
def parse_site_products():
    try:
        response = requests.get("https://mytoy66.ru/group?type=latest", timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select(".item-product")

        products = []
        for item in items:
            title = item.select_one(".product-title").get_text(strip=True)
            price = int(item.select_one(".price").get_text(strip=True).replace("₽", "").replace(" ", ""))
            photo = item.select_one("img")["src"]
            link = item.select_one("a")["href"]
            description = item.select_one(".product-description")
            description_text = description.get_text(strip=True) if description else None

            if price >= 300 and photo:
                if not description_text:
                    description_text = generate_description(title, photo)
                products.append({
                    "title": title,
                    "price": price,
                    "description": description_text,
                    "photo": photo,
                    "link": f"https://mytoy66.ru{link}"
                })
        return products
    except Exception as e:
        logging.error(f"Ошибка при парсинге сайта: {e}")
        return []

# --- Парсинг YML ---
def parse_yml_products():
    try:
        response = requests.get("https://mytoy66.ru/integration?int=avito&name=avitoo", timeout=10)
        root = ET.fromstring(response.content)
        products = []

        for offer in root.findall(".//offer"):
            price = int(offer.find("price").text)
            picture = offer.find("picture").text if offer.find("picture") is not None else ""
            title = offer.find("name").text
            description = offer.find("description").text if offer.find("description") is not None else ""
            link = offer.get("url")

            if price >= 300 and picture:
                if not description:
                    description = generate_description(title, picture)
                products.append({
                    "title": title,
                    "price": price,
                    "description": description,
                    "photo": picture,
                    "link": link
                })
        return products
    except Exception as e:
        logging.error(f"Ошибка при парсинге YML: {e}")
        return []

# --- Генерация описания ---
def generate_description(title, image_url):
    return f"Уникальный товар: {title}. Отличный выбор для вас! Подробности — по кнопке ниже."

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот готов к работе. /next /pause /resume /status /log")

async def next_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await post_next_product(context)

async def pause_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global posting_paused
    if update.effective_user.id != ADMIN_ID:
        return
    posting_paused = True
    await update.message.reply_text("Публикация приостановлена.")

async def resume_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global posting_paused
    if update.effective_user.id != ADMIN_ID:
        return
    posting_paused = False
    await update.message.reply_text("Публикация возобновлена.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    status = "приостановлена" if posting_paused else "активна"
    await update.message.reply_text(f"Публикация сейчас {status}. Индекс товара: {current_product_index}")

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Лог пуст (или подключите файл лога).")

# --- Постинг товара ---
async def post_next_product(context: ContextTypes.DEFAULT_TYPE):
    global current_product_index, products_cache
    if posting_paused:
        return
    if not products_cache:
        products_cache = parse_site_products()
        if not products_cache:
            products_cache = parse_yml_products()
        current_product_index = 0

    if not products_cache:
        await context.bot.send_message(chat_id=ADMIN_ID, text="Нет доступных товаров для публикации.")
        return

    if current_product_index >= len(products_cache):
        current_product_index = 0

    product = products_cache[current_product_index]
    current_product_index += 1

    text = f"<b>{product['title']}</b>\nЦена: {product['price']}₽\n\n{product['description']}"
    button = [[InlineKeyboardButton("Купить", url=product["link"])]]
    reply_markup = InlineKeyboardMarkup(button)

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=product["photo"],
        caption=text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

# --- Планировщик ---
async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    await post_next_product(context)

# --- Запуск ---
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("next", next_post))
    application.add_handler(CommandHandler("pause", pause_posting))
    application.add_handler(CommandHandler("resume", resume_posting))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("log", log))

    application.job_queue.run_daily(
        daily_post,
        time=datetime.time(hour=12, minute=0, tzinfo=datetime.timezone(datetime.timedelta(hours=3)))  # МСК
    )

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await application.updater.idle()

if __name__ == '__main__':
    asyncio.run(main())
