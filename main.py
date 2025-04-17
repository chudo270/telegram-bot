import logging
import asyncio
import os
import requests
import xml.etree.ElementTree as ET
from datetime import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    Application
)

# Настройки
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")
YML_URL = "https://cdn.mysitemapgenerator.com/shareapi/yml/16046306746_514"
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
CHANNEL_ID = "@myttoy66"
ADMIN_ID = 487591931

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные
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
                                "picture": picture,
                                "url": url,
                                "category": category,
                                "description": description
                            })
                    except ValueError:
                        continue
            global product_queue
            product_queue = products
            logger.info(f"Загружено товаров: {len(products)}")
        else:
            logger.error(f"Ошибка загрузки YML: {response.status_code}")
    except Exception as e:
        logger.error(f"Ошибка при загрузке YML: {e}")
    return []

# Обёртка для загрузки из всех источников
def load_products_from_sources():
    load_products_from_yml(YML_URL)

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

        response = requests.post(
            "https://gigachat.devices....bank.ru/api/v1/chat/completions",
            json=payload,
            headers=headers
        )
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
    generated_description = generate_description(
        product['name'],
        product.get("description", "")
    )

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
    await update.message.reply_text(
        f"В очереди: {len(product_queue)} товаров.",
        reply_markup=main_menu
    )

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
        # фото + подпись
        photo = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=caption)
    else:
        # просто текст
        await context.bot.send_message(chat_id=CHANNEL_ID, text=update.message.text)

# Обработка кнопок
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "next":
        await publish_next_product(context)
    elif action == "pause":
        await pause(update, context)
    elif action == "resume":
        await resume(update, context)
    elif action == "queue":
        await show_queue(update, context)
    elif action == "status":
        await status(update, context)
    elif action == "log":
        await log(update, context)
    elif action == "skip":
        if product_queue:
            skipped = product_queue.pop(0)
            await query.edit_message_text(
                f"Пропущен товар: {skipped['name']}",
                reply_markup=main_menu
            )
        else:
            await query.edit_message_text("Очередь пуста.", reply_markup=main_menu)
    elif action == "broadcast":
        context.user_data["broadcast_mode"] = True
        await query.edit_message_text("Отправьте сообщение (или фото с подписью) для рассылки.")

# Регистрация хэндлеров
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

# Запуск планировщика на старте
async def on_startup(application: Application):
    load_products_from_sources()
    start_scheduler(application)
    logger.info("Бот запущен и готов к работе.")

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

# Точка входа
async def main():
    app = build_application()
    await app.initialize()
    await on_startup(app)
    # Регистрируем вебхук в Telegram
    await app.bot.set_webhook(f"{WEBHOOK_URL}/{BOT_TOKEN}")
    # Запускаем встроенный HTTP‑сервер для обработки POST от Telegram
    PORT = int(os.environ.get("PORT", 8080))
    await app.start_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url_path=f"/{BOT_TOKEN}"
    )
    # Ожидание остановки
    await app.idle()

if __name__ == "__main__":
    asyncio.run(main())
     except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен вручную")
    except Exception as e:
        logging.exception(f"Произошла критическая ошибка: {e}")
