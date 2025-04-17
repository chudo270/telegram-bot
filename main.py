import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
import asyncio
import os
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
import requests
import xml.etree.ElementTree as ET
BOT_TOKEN = os.getenv("BOT_TOKEN")
import nest_asyncio
nest_asyncio.apply()
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from telegram.ext import Application
from datetime import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Настройки
CHANNEL_ID = "@myttoy66"
ADMIN_ID = 487591931
SITE_URL = "https://myttoy66.ru"
YML_URL = "https://cdn.mysitemapgenerator.com/shareapi/yml/16046306746_514"
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")

product_queue = []
paused = False

# Главное меню
main_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("▶️ Следующий", callback_data="next")],
    [InlineKeyboardButton("⏸ Пауза", callback_data="pause"),
     InlineKeyboardButton("▶️ Возобновить", callback_data="resume")],
    [InlineKeyboardButton("📦 Очередь", callback_data="queue"),
     InlineKeyboardButton("⏭ Пропустить", callback_data="skip")],
    [InlineKeyboardButton("📊 Статус", callback_data="status"),
     InlineKeyboardButton("📝 Логи", callback_data="log")],
    [InlineKeyboardButton("📢 Рассылка", callback_data="broadcast")],
    [InlineKeyboardButton("🧠 Нейросеть", callback_data="ai")]
])

# Загрузка товаров из YML
def load_products_from_yml(yml_url):
    try:
        response = requests.get(yml_url)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            products = []

            for offer in root.findall(".//offer"):
                price = offer.findtext("price")
                picture = offer.findtext("picture")
                name = offer.findtext("name")
                url = offer.findtext("url")
                category = offer.findtext("categoryId")
                description = offer.findtext("description", "")

                if price and picture:
                    try:
                        price = int(float(price))
                        if price >= 300:
                            products.append({
                                "id": offer.attrib.get("id"),
                                "name": name,
                                "price": price,
                                "url": url,
                                "category": category,
                                "picture": picture,
                                "description": description or ""
                            })
                    except ValueError:
                        continue
            return products
    except Exception as e:
        logging.error(f"Ошибка при загрузке YML: {e}")
    return []

# Генерация описания через GigaChat
def generate_description(name, description):
    try:
        prompt = f"Сделай короткое продающее описание товара по названию: {name}"
        if description:
            prompt += f" и описанию: {description}"

        headers = {
            "Authorization": f"Bearer {GIGACHAT_AUTH_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "GigaChat",
            "messages": [
                {"role": "system", "content": "Ты — маркетолог, создающий короткие продающие описания."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 1.0,
            "top_p": 0.9,
            "n": 1
        }

        response = requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions", json=payload, headers=headers)
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            logging.warning(f"GigaChat ошибка: {response.status_code} — {response.text}")
    except Exception as e:
        logging.error(f"Ошибка генерации описания: {e}")

    return "Отличный выбор по хорошей цене!"
    
# Публикация товара в канал
async def publish_next_product(context: ContextTypes.DEFAULT_TYPE):
    global paused, product_queue
    if paused or not product_queue:
        return

    product = product_queue.pop(0)
    title = f"<b>{product['name']}</b>"
    price = f"<b>{product['price']} ₽</b>"

    # Генерация описания
    generated_description = generate_description(product['name'], product.get("description", ""))

    text = f"{title}\n\n{generated_description}\n\n{price}"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Купить", url=product['url'])]
    ])

    try:
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=product['picture'],
            caption=text,
            reply_markup=buttons,
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка публикации товара: {e}")

# Команды управления
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен.", reply_markup=main_menu)

async def next_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await publish_next_product(context)

async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = True
    await update.message.reply_text("Публикации приостановлены.", reply_markup=main_menu)

async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = False
    await update.message.reply_text("Публикации возобновлены.", reply_markup=main_menu)
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    state = "⏸ Пауза" if paused else "▶️ Активен"
    await update.message.reply_text(f"Текущий статус: {state}", reply_markup=main_menu)

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Логи не ведутся. Все стабильно.", reply_markup=main_menu)

async def show_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(f"В очереди: {len(product_queue)} товаров.", reply_markup=main_menu)

# Рассылка
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["broadcast_mode"] = True
    await update.message.reply_text("Отправьте сообщение (или фото с подписью) для рассылки.")

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not context.user_data.get("broadcast_mode"):
        return

    context.user_data["broadcast_mode"] = False

    if update.message.photo:
        photo = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=caption)
    elif update.message.text:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=update.message.text)

    await update.message.reply_text("Сообщение отправлено.", reply_markup=main_menu)

# Кнопки меню
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return

    action = query.data

    if action == "next":
        await publish_next_product(context)
        await query.edit_message_text("Следующий товар опубликован.", reply_markup=main_menu)
    elif action == "pause":
        global paused
        paused = True
        await query.edit_message_text("Пауза активирована.", reply_markup=main_menu)
    elif action == "resume":
        paused = False
        await query.edit_message_text("Публикация возобновлена.", reply_markup=main_menu)
    elif action == "queue":
        await query.edit_message_text(f"В очереди: {len(product_queue)} товаров.", reply_markup=main_menu)
    elif action == "status":
        state = "⏸ Пауза" if paused else "▶️ Активен"
        await query.edit_message_text(f"Текущий статус: {state}", reply_markup=main_menu)
    elif action == "log":
        await query.edit_message_text("Логи не ведутся. Все стабильно.", reply_markup=main_menu)
    elif action == "skip":
        if product_queue:
            skipped = product_queue.pop(0)
            await query.edit_message_text(f"Пропущен товар: {skipped['name']}", reply_markup=main_menu)
        else:
            await query.edit_message_text("Очередь пуста.", reply_markup=main_menu)
    elif action == "broadcast":
        context.user_data["broadcast_mode"] = True
        await query.edit_message_text("Отправьте сообщение (или фото с подписью) для рассылки.")
def build_application():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("next", next_product))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("log", log))
    application.add_handler(CommandHandler("queue", show_queue))
    application.add_handler(CommandHandler("broadcast", broadcast_start))
    application.add_handler(MessageHandler(filters.ALL, broadcast_message))
    application.add_handler(CallbackQueryHandler(button_callback))

    return application


def start_scheduler(application: Application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: application.create_task(publish_next_product(application)),
        trigger='cron',
        hour=12,
        minute=0,
        timezone='Europe/Moscow'
    )
    scheduler.start()

async def on_startup(application: Application):
    load_products_from_sources()
    start_scheduler(application)
    logging.info("Бот запущен и готов к работе.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    app = build_application()

    # Регистрируем обработчик webhook
    app.router.add_post("/webhook", app.webhook_handler())

    async def main():
        await app.initialize()
        await app.bot.set_webhook(WEBHOOK_URL)
        await app.start()
        logger.info("Webhook установлен и бот запущен.")
        await asyncio.get_event_loop().run_forever()

    asyncio.run(main())
