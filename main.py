import os
import logging
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Настройки
TOKEN = "7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0"
ADMIN_ID = 487591931
CHANNEL_ID = "@myttoy66"
MAIN_URL = "https://mytoy66.ru/group?type=latest"
RESERVE_YML = "https://mytoy66.ru/integration?int=avito&name=avitoo"

# Очередь товаров
product_queue = []

# Логгирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# HTML-парсинг
def fetch_products_from_html():
    products = []
    try:
        response = requests.get(MAIN_URL)
        soup = BeautifulSoup(response.content, "html.parser")
        items = soup.select(".product-wrapper")

        for item in items:
            name_tag = item.select_one(".product-name")
            price_tag = item.select_one(".price")
            img_tag = item.select_one("img")
            link_tag = item.select_one("a")

            if not name_tag or not price_tag or not img_tag:
                continue

            name = name_tag.get_text(strip=True)
            price = int(''.join(filter(str.isdigit, price_tag.get_text())))
            image = img_tag.get("src")
            link = link_tag.get("href")

            if price >= 300 and image:
                products.append({
                    "name": name,
                    "price": price,
                    "image": image,
                    "link": f"https://mytoy66.ru{link}"
                })
    except Exception as e:
        logger.error(f"Ошибка при парсинге HTML: {e}")
    return products

# Кнопки
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("Следующий товар", callback_data='next')],
        [InlineKeyboardButton("Пауза", callback_data='pause')],
        [InlineKeyboardButton("Статус", callback_data='status')],
        [InlineKeyboardButton("Лог", callback_data='log')],
        [InlineKeyboardButton("Написать", callback_data='write')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("Бот запущен", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cmd = query.data

    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("Нет доступа")
        return

    if cmd == "next":
        await send_next_product(context)
    elif cmd == "pause":
        await query.edit_message_text("Пауза активирована")
    elif cmd == "status":
        await query.edit_message_text("Бот работает. Очередь товаров: " + str(len(product_queue)))
    elif cmd == "log":
        await query.edit_message_text("Логирование активно.")
    elif cmd == "write":
        context.user_data["writing"] = True
        await query.edit_message_text("Введите текст, который хотите отправить в канал:")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if context.user_data.get("writing"):
        text = update.message.text
        await context.bot.send_message(CHANNEL_ID, text)
        await update.message.reply_text("Отправлено в канал.")
        context.user_data["writing"] = False

# Публикация товара
async def send_next_product(context: ContextTypes.DEFAULT_TYPE):
    global product_queue
    if not product_queue:
        product_queue = fetch_products_from_html()

    if not product_queue:
        await context.bot.send_message(ADMIN_ID, "Нет товаров для публикации.")
        return

    product = product_queue.pop(0)
    text = f"<b>{product['name']}</b>\nЦена: {product['price']}₽\n<a href='{product['link']}'>Посмотреть товар</a>"
    await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=product["image"],
        caption=text,
        parse_mode="HTML"
    )

# Планировщик
scheduler = AsyncIOScheduler()
scheduler.add_job(send_next_product, 'cron', hour=12, minute=0, args=[None])  # каждый день в 12:00

# Инициализация
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

# Запуск
if __name__ == "__main__":
    product_queue = fetch_products_from_html()
    scheduler.start()
    app.run_polling()
