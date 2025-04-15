import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import asyncio
import datetime
import requests
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread

# === Web-сервер для "пробуждения" ===
app = Flask('')

@app.route('/')
def home():
    return "Я жив!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# === Конфигурация ===
BOT_TOKEN = 'твой_токен'
ADMIN_ID = 487591931
posting_paused = False
current_product_index = 0
products_cache = []

# === Логгирование ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# === Пример генерации описания ===
def generate_description(title):
    return f"Это отличный товар: {title}. Отличный выбор!"

# === Загрузка товаров ===
def load_products():
    global products_cache
    products_cache.clear()

    try:
        html = requests.get("https://mytoy66.ru/group?type=latest", timeout=10).text
        soup = BeautifulSoup(html, "html.parser")
        for item in soup.select(".item-product"):
            try:
                title = item.select_one(".title").text.strip()
                price_text = item.select_one(".price").text.strip().replace("₽", "").replace(" ", "")
                price = int(price_text)
                if price < 300:
                    continue
                image = item.select_one("img")["src"]
                if not image:
                    continue
                description = item.select_one(".description")
                desc = description.text.strip() if description else generate_description(title)
                link = item.select_one("a")["href"]
                full_link = f"https://mytoy66.ru{link}"

                products_cache.append({
                    "title": title,
                    "price": price,
                    "description": desc,
                    "photo": image,
                    "link": full_link
                })
            except Exception as e:
                continue
    except Exception as e:
        logging.error(f"Ошибка при загрузке товаров: {e}")

# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот активен. Используйте /next, /pause, /resume, /status, /log.")

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
    status_text = "приостановлена" if posting_paused else "активна"
    await update.message.reply_text(f"Публикация {status_text}. Текущий товар: {current_product_index + 1}/{len(products_cache)}")

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Лог пуст.")

# === Публикация ===
async def post_next_product(context: ContextTypes.DEFAULT_TYPE):
    global current_product_index
    if posting_paused or not products_cache:
        return

    if current_product_index >= len(products_cache):
        current_product_index = 0

    product = products_cache[current_product_index]
    current_product_index += 1

    message = f"<b>{product['title']}</b>\nЦена: {product['price']}₽\n\n{product['description']}"
    keyboard = [[InlineKeyboardButton("Купить", url=product["link"])]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=product['photo'],
        caption=message,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# === Планировщик ===
async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    load_products()
    await post_next_product(context)

# === Основной запуск ===
async def main():
    load_products()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("next", next_post))
    application.add_handler(CommandHandler("pause", pause_posting))
    application.add_handler(CommandHandler("resume", resume_posting))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("log", log))

    application.job_queue.run_daily(daily_post, time=datetime.time(hour=12, minute=0, tzinfo=datetime.timezone.utc))

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await application.updater.idle()

# === Запуск ===
if __name__ == '__main__':
    keep_alive()
    asyncio.run(main())
