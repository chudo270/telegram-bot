import logging
import asyncio
import datetime
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

BOT_TOKEN = '7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0'
ADMIN_ID = 487591931

SITE_URL = "https://mytoy66.ru/group?type=latest"
YML_URL = "https://mytoy66.ru/integration?int=avito&name=avitoo"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

posting_paused = False
current_product_index = 0
products_cache = []

# Генерация описания
def generate_description(title):
    return f"Отличный выбор! {title} — качество, проверенное временем. Подходит для подарка и повседневного использования."

# Парсинг с сайта
def fetch_products_from_site():
    result = []
    try:
        r = requests.get(SITE_URL)
        soup = BeautifulSoup(r.text, 'html.parser')
        cards = soup.select('.product-card')

        for card in cards:
            title = card.select_one('.card-title').get_text(strip=True)
            price_text = card.select_one('.price').get_text(strip=True).replace('₽', '').replace(' ', '')
            link = card.select_one('a.card')['href']
            photo_tag = card.select_one('img')
            photo = photo_tag['src'] if photo_tag else ''
            price = int(price_text) if price_text.isdigit() else 0
            description = generate_description(title)

            if photo and price >= 300:
                result.append({
                    'title': title,
                    'price': price,
                    'description': description,
                    'photo': photo,
                    'url': "https://mytoy66.ru" + link
                })
    except Exception as e:
        logging.error(f"Ошибка при парсинге сайта: {e}")
    return result

# Парсинг из YML
def fetch_products_from_yml():
    result = []
    try:
        r = requests.get(YML_URL)
        tree = ET.fromstring(r.content)
        offers = tree.findall(".//offer")

        for offer in offers:
            title = offer.findtext("name")
            description = offer.findtext("description") or generate_description(title)
            photo = offer.findtext("picture")
            price = int(float(offer.findtext("price", "0")))
            url = offer.findtext("url")

            if photo and price >= 300:
                result.append({
                    'title': title,
                    'price': price,
                    'description': description,
                    'photo': photo,
                    'url': url
                })
    except Exception as e:
        logging.error(f"Ошибка при парсинге YML: {e}")
    return result

async def post_next_product(context: ContextTypes.DEFAULT_TYPE):
    global current_product_index, products_cache

    if posting_paused:
        return

    if not products_cache:
        products_cache = fetch_products_from_site()
        if not products_cache:
            products_cache = fetch_products_from_yml()

    if current_product_index >= len(products_cache):
        current_product_index = 0

    if not products_cache:
        return

    product = products_cache[current_product_index]
    current_product_index += 1

    message = f"<b>{product['title']}</b>\nЦена: {product['price']}₽\n\n{product['description']}"
    keyboard = [[InlineKeyboardButton("Купить", url=product['url'])]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=product['photo'],
        caption=message,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен. Используйте /next, /pause, /resume, /status, /log.")

async def next_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await post_next_product(context)

async def pause_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global posting_paused
    if update.effective_user.id == ADMIN_ID:
        posting_paused = True
        await update.message.reply_text("Публикация приостановлена.")

async def resume_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global posting_paused
    if update.effective_user.id == ADMIN_ID:
        posting_paused = False
        await update.message.reply_text("Публикация возобновлена.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        status = "приостановлена" if posting_paused else "активна"
        await update.message.reply_text(f"Публикация {status}. Текущий индекс: {current_product_index}/{len(products_cache)}")

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("Логирование включено. Подробности — в логах сервера.")

# Планировщик
async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    await post_next_product(context)

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_post))
    app.add_handler(CommandHandler("pause", pause_posting))
    app.add_handler(CommandHandler("resume", resume_posting))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("log", log))

    app.job_queue.run_daily(daily_post, time=datetime.time(hour=9, tzinfo=datetime.timezone.utc))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()

if __name__ == '__main__':
    asyncio.run(main())
