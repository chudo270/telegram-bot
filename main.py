import telegram
import logging
import asyncio
import requests
import random
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackContext

# Логирование
logging.basicConfig(level=logging.INFO)

# Настройки Telegram
BOT_TOKEN = "7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0"
CHANNEL_ID = "@myttoy66"  # Укажи свой канал
ADMIN_ID = 487591931

# Настройки API Moguta
MOGUTA_DOMAIN = "https://mytoy66.ru"
API_TOKEN = "565df1b1313ac458b0ef1a7ef16c4bc4"
SECRET_KEY = "mySecretKey12345"

# Резервный источник
YML_URL = "https://mytoy66.ru/integration?int=avito&name=avitoo"

# Глобальные переменные
product_queue = []
paused = False
log_messages = []

# Генерация описания
def generate_description(title: str) -> str:
    return f"Отличный товар: {title}. Прекрасно подойдёт для вас!"

# Получение товаров из Moguta API
def fetch_products_from_api():
    url = f"{MOGUTA_DOMAIN}/api/products?userToken={API_TOKEN}&inJSON=true"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        products = data.get("data", {}).get("catalog", [])
        valid_products = []

        for product in products:
            title = product.get("title")
            price = product.get("price")
            image = product.get("image_url") or product.get("images", [None])[0]
            description = product.get("description") or generate_description(title)
            url = f"{MOGUTA_DOMAIN}/{product.get('category_url', '')}/{product.get('url', '')}"

            if not image or not title or not price:
                continue

            valid_products.append({
                "title": title,
                "price": price,
                "description": description,
                "image": image,
                "url": url
            })

        return valid_products
    except Exception as e:
        log_messages.append(f"[{datetime.now()}] Ошибка API: {e}")
        return []

# Резерв: Получение из YML
def fetch_products_from_yml():
    try:
        response = requests.get(YML_URL)
        if response.ok:
            # Здесь могла бы быть парсинг YML, но упрощаем
            return []
    except Exception as e:
        log_messages.append(f"[{datetime.now()}] Ошибка YML: {e}")
    return []

# Постинг в Telegram
async def post_product(context: CallbackContext = None):
    global product_queue, paused

    if paused or not product_queue:
        return

    product = product_queue.pop(0)
    text = f"*{product['title']}*\n\n{product['description']}\n\nЦена: {product['price']}₽"
    buttons = [[InlineKeyboardButton("Купить", url=product['url'])]]
    reply_markup = InlineKeyboardMarkup(buttons)

    try:
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=product['image'],
            caption=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        log_messages.append(f"[{datetime.now()}] Отправлен товар: {product['title']}")
    except Exception as e:
        log_messages.append(f"[{datetime.now()}] Ошибка отправки: {e}")

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    keyboard = [
        [InlineKeyboardButton("▶️ Следующий", callback_data="next"),
         InlineKeyboardButton("⏸ Пауза", callback_data="pause")],
        [InlineKeyboardButton("▶ Продолжить", callback_data="resume"),
         InlineKeyboardButton("ℹ️ Статус", callback_data="status")],
        [InlineKeyboardButton("📋 Лог", callback_data="log")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Панель управления:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    if query.data == "next":
        await post_product(context)
    elif query.data == "pause":
        paused = True
        await query.edit_message_text("Автопостинг приостановлен.")
    elif query.data == "resume":
        paused = False
        await query.edit_message_text("Автопостинг возобновлён.")
    elif query.data == "status":
        msg = f"Пауза: {'Да' if paused else 'Нет'}\nТоваров в очереди: {len(product_queue)}"
        await query.edit_message_text(msg)
    elif query.data == "log":
        log_text = "\n".join(log_messages[-10:]) or "Лог пуст."
        await query.edit_message_text(log_text)

# Загрузка товаров
def load_products():
    products = fetch_products_from_api()
    if not products:
        products = fetch_products_from_yml()
    random.shuffle(products)
    return products

# Основной запуск
async def main():
    global product_queue
    product_queue = load_products()

    app = Application.builder().token(BOT_TOKEN).build()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(post_product, CronTrigger(hour=12, minute=0), args=[app.bot])
    scheduler.start()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^/next$"), lambda u, c: post_product(c)))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^/pause$"), lambda u, c: set_pause(True)))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^/resume$"), lambda u, c: set_pause(False)))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^/status$"), status))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^/log$"), log))
    app.add_handler(MessageHandler(filters.ALL, lambda u, c: None))  # глушим остальные

    from telegram.ext import CallbackQueryHandler  # Добавить в начало файла

    app.add_handler(CallbackQueryHandler(button_handler))


    await app.run_polling()

# Хелп-функции
def set_pause(state: bool):
    global paused
    paused = state

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = f"Пауза: {'Да' if paused else 'Нет'}\nТоваров в очереди: {len(product_queue)}"
    await update.message.reply_text(msg)

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = "\n".join(log_messages[-10:]) or "Лог пуст."
    await update.message.reply_text(text)

if __name__ == "__main__":
    import nest_asyncio
nest_asyncio.apply()
asyncio.get_event_loop().run_until_complete(main())

