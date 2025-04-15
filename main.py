import asyncio
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = "7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0"
CHANNEL_ID = "@myttoy66"
ADMIN_ID = 487591931

logging.basicConfig(level=logging.INFO)
application = Application.builder().token(TOKEN).build()

scheduler = AsyncIOScheduler()
scheduler.start()

write_mode_users = set()

def get_products_from_site():
    url = "https://mytoy66.ru/group?type=latest"
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        products = []
        for product in soup.select(".product-item"):
            title = product.select_one(".product-title a").text.strip()
            price_tag = product.select_one(".price")
            image_tag = product.select_one(".product-image img")
            if not price_tag or not image_tag:
                continue
            price_text = price_tag.text.replace("₽", "").replace(" ", "").strip()
            price = int("".join(filter(str.isdigit, price_text)))
            if price < 300:
                continue
            image = image_tag['src']
            link = product.select_one(".product-title a")['href']
            url_full = "https://mytoy66.ru" + link
            products.append({
                "title": title,
                "price": price,
                "image": image,
                "url": url_full
            })
        return products
    except Exception as e:
        logging.error(f"Ошибка парсинга: {e}")
        return []

product_index = 0

async def post_product(context: ContextTypes.DEFAULT_TYPE):
    global product_index
    products = get_products_from_site()
    if not products:
        await context.bot.send_message(chat_id=ADMIN_ID, text="Нет подходящих товаров.")
        return
    if product_index >= len(products):
        product_index = 0
    product = products[product_index]
    caption = f"<b>{product['title']}</b>\nЦена: {product['price']}₽\n<a href='{product['url']}'>Подробнее</a>"
    await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=product['image'],
        caption=caption,
        parse_mode='HTML'
    )
    product_index += 1

@application.command_handler("start")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Следующий товар", callback_data="next")],
        [InlineKeyboardButton("Пауза", callback_data="pause")],
        [InlineKeyboardButton("Продолжить", callback_data="resume")],
        [InlineKeyboardButton("Статус", callback_data="status")],
        [InlineKeyboardButton("Лог", callback_data="log")],
        [InlineKeyboardButton("Написать", callback_data="write_mode")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

@application.callback_query_handler(lambda query: query.data == "next")
async def next_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await post_product(context)
    await update.callback_query.answer("Отправлен следующий товар.")

@application.callback_query_handler(lambda query: query.data == "pause")
async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scheduler.pause()
    await update.callback_query.answer("Публикации приостановлены.")

@application.callback_query_handler(lambda query: query.data == "resume")
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scheduler.resume()
    await update.callback_query.answer("Публикации возобновлены.")

@application.callback_query_handler(lambda query: query.data == "status")
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = "включен" if scheduler.running else "выключен"
    await update.callback_query.answer(f"Автопостинг: {state}")

@application.callback_query_handler(lambda query: query.data == "log")
async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("Логов пока нет.")

@application.callback_query_handler(lambda query: query.data == "write_mode")
async def enter_write_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    write_mode_users.add(user_id)
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Вы вошли в режим написания. Всё, что вы напишете, будет опубликовано в канал.")

@application.message_handler(filters.TEXT & ~filters.COMMAND)
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in write_mode_users:
        text = update.message.text
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"[Реклама]\n{text}")
        await update.message.reply_text("Сообщение отправлено в канал.")

# Расписание: каждый день в 12:00 по МСК
scheduler.add_job(lambda: application.create_task(post_product(None)), trigger='cron', hour=12, minute=0)

if __name__ == '__main__':
    application.run_polling()
