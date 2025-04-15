import datetime
import asyncio
import logging
import requests
import feedparser
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# === Настройки ===
TOKEN = '7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0'
ADMIN_ID = 487591931
CHANNEL_ID = '@mytoy_channel'  # Замени на название своего канала
SITE_URL = 'https://mytoy66.ru/group?type=latest'
YML_URL = 'https://mytoy66.ru/integration?int=avito&name=avitoo'

# === Логгирование ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Функция генерации описания ===
def generate_description(name, image_url):
    return f'Отличный товар: {name}. Подходит для любого возраста!'

# === Парсинг сайта ===
def fetch_products_from_site():
    try:
        response = requests.get(SITE_URL)
        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.select('.product-item')
        products = []

        for item in items:
            name = item.select_one('.product-title').text.strip()
            price = int(item.select_one('.price').text.replace('₽', '').strip().replace(' ', ''))
            img_tag = item.select_one('img')
            image = img_tag['src'] if img_tag else ''
            link_tag = item.select_one('a')
            link = 'https://mytoy66.ru' + link_tag['href'] if link_tag else ''
            if image and price >= 300:
                products.append({
                    'name': name,
                    'price': price,
                    'image': image,
                    'link': link,
                    'description': generate_description(name, image)
                })

        return products
    except Exception as e:
        logger.error(f'Ошибка при парсинге сайта: {e}')
        return []

# === Парсинг YML ===
def fetch_products_from_yml():
    try:
        data = feedparser.parse(YML_URL)
        products = []

        for entry in data.entries:
            name = entry.title
            price = int(entry.get('g_price', '0'))
            image = entry.get('g_image_link', '')
            link = entry.link
            if image and price >= 300:
                products.append({
                    'name': name,
                    'price': price,
                    'image': image,
                    'link': link,
                    'description': generate_description(name, image)
                })

        return products
    except Exception as e:
        logger.error(f'Ошибка при парсинге YML: {e}')
        return []

# === Публикация товара ===
async def post_product(context: ContextTypes.DEFAULT_TYPE):
    products = fetch_products_from_site()
    if not products:
        products = fetch_products_from_yml()
    if not products:
        return

    product = products[0]
    text = f"<b>{product['name']}</b>\n\n{product['description']}\n\nЦена: {product['price']} ₽"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Купить", url=product['link'])]
    ])

    await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=product['image'],
        caption=text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен!")

async def next_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await post_product(context)
    await update.message.reply_text("Товар опубликован.")

# === Главная функция ===
async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_post))

    job_queue = app.job_queue
    job_queue.run_daily(post_product, time=datetime.time(hour=12, minute=0))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.idle()

if __name__ == '__main__':
    asyncio.run(main())
