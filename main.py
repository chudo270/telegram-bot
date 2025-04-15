import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import logging
import xml.etree.ElementTree as ET
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import time

# Настройки
TOKEN = "7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0"
ADMIN_ID = 487591931
CHANNEL_ID = "@myttoy66"
WEBHOOK_PATH = "/webhook/myttoy66"
WEBHOOK_URL = f"https://worker-production-c8d5.up.railway.app{WEBHOOK_PATH}"

# Очередь товаров
queue = []
is_paused = False

# Логгирование
logging.basicConfig(level=logging.INFO)

# Генерация кнопок
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Следующий", callback_data="next")],
        [InlineKeyboardButton("⏸ Пауза", callback_data="pause")],
        [InlineKeyboardButton("▶ Продолжить", callback_data="resume")],
        [InlineKeyboardButton("📋 Статус", callback_data="status")],
        [InlineKeyboardButton("✍ Написать", callback_data="write")],
        [InlineKeyboardButton("🧾 Логи", callback_data="log")]
    ])

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("Панель управления:", reply_markup=get_main_keyboard())

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_paused
    query = update.callback_query
    await query.answer()
    data = query.data

    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("Доступ запрещён")
        return

    if data == "next":
        await post_next_item(context)
    elif data == "pause":
        is_paused = True
        await query.edit_message_text("Публикация приостановлена", reply_markup=get_main_keyboard())
    elif data == "resume":
        is_paused = False
        await query.edit_message_text("Публикация возобновлена", reply_markup=get_main_keyboard())
    elif data == "status":
        status = "Пауза" if is_paused else "Активен"
        await query.edit_message_text(f"Текущий статус: {status}\nОсталось товаров: {len(queue)}", reply_markup=get_main_keyboard())
    elif data == "log":
        await query.edit_message_text("Лог пока не реализован", reply_markup=get_main_keyboard())
    elif data == "write":
        context.user_data["awaiting_ad"] = True
        await query.edit_message_text("Напишите текст, который нужно отправить в канал.", reply_markup=get_main_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if context.user_data.get("awaiting_ad"):
        text = update.message.text
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text)
        context.user_data["awaiting_ad"] = False
        await update.message.reply_text("Отправлено!", reply_markup=get_main_keyboard())

# Загрузка из YML
async def get_products():
    YML_URL = "https://mytoy66.ru/integration?int=avito&name=avitoo"
    products = []

    async with aiohttp.ClientSession() as session:
        async with session.get(YML_URL) as resp:
            text = await resp.text()

    root = ET.fromstring(text)
    for offer in root.findall(".//offer"):
        name = offer.findtext("name")
        price = float(offer.findtext("price", "0"))
        description = offer.findtext("description", "")
        image = offer.findtext("picture")
        url = offer.findtext("url")

        # Фильтрация
        if not image or price < 300:
            continue

        # Генерация описания при отсутствии
        if not description:
            description = f"Подробности: {name}"

        products.append({
            "name": name,
            "price": price,
            "description": description,
            "image": image,
            "link": url
        })

    return products

# Загрузка товаров
async def load_products():
    global queue
    queue = await get_products()
    logging.info(f"Загружено товаров: {len(queue)}")

# Публикация
async def post_next_item(context: ContextTypes.DEFAULT_TYPE):
    global queue
    if is_paused or not queue:
        return
    item = queue.pop(0)
    text = f"<b>{item['name']}</b>\n{item['price']} ₽\n\n{item['description']}"
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("Купить", url=item["link"])]])
    await context.bot.send_photo(chat_id=CHANNEL_ID, photo=item["image"], caption=text, parse_mode="HTML", reply_markup=buttons)

# Планировщик
def schedule_posts(app: Application):
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(lambda: app.create_task(post_next_item(app.bot)), trigger='cron', hour=12, minute=0)
    scheduler.start()

# Webhook запуск
async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    await load_products()
    schedule_posts(app)

    # Установка Webhook
    await app.bot.set_webhook(WEBHOOK_URL)
    await app.run_webhook(
        listen="0.0.0.0",
        port=8080,
        webhook_path=WEBHOOK_PATH,
        url_path=WEBHOOK_PATH,
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if str(e).startswith("This event loop is already running"):
            import nest_asyncio
            nest_asyncio.apply()
            asyncio.get_event_loop().run_until_complete(main())
