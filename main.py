import asyncio
import logging
import os
import requests
import xml.etree.ElementTree as ET
import openai
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_log.txt'
)
logger = logging.getLogger(__name__)

# Настройки из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "487591931"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@myttoy66")
YML_URL = os.getenv("YML_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

keyboard = [
    [InlineKeyboardButton("▶️ Следующий пост", callback_data="next")],
    [InlineKeyboardButton("⏸ Пауза", callback_data="pause"), InlineKeyboardButton("✅ Возобновить", callback_data="resume")],
    [InlineKeyboardButton("📋 Очередь постов", callback_data="queue")],
    [InlineKeyboardButton("📨 Написать сообщение", callback_data="broadcast")],
    [InlineKeyboardButton("📄 Лог", callback_data="log")],
    [InlineKeyboardButton("ℹ️ Статус", callback_data="status")],
    [InlineKeyboardButton("⏭ Пропустить товар", callback_data="skip")],
]
menu = InlineKeyboardMarkup(keyboard)
# Генерация краткого описания с помощью OpenAI (всегда)
def generate_short_description(name: str, description: str = "") -> str:
    try:
        prompt = (
            f"Создай краткое продающее описание товара на русском языке. "
            f"Название: {name}\nОписание: {description}"
        )
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты маркетолог. Пиши лаконичные продающие тексты."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=60,
            temperature=0.7,
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        logger.error(f"Ошибка генерации описания: {e}")
        return description or "Описание временно недоступно."

# Получение товаров из YML-файла
def fetch_products_from_yml():
    try:
        response = requests.get(YML_URL)
        response.raise_for_status()
        tree = ET.fromstring(response.content)

        products = []
        for offer in tree.findall(".//offer"):
            name = offer.findtext("name")
            price = offer.findtext("price")
            picture = offer.findtext("picture")
            url = offer.findtext("url")
            description = offer.findtext("description") or ""

            if not picture or not price or float(price) < 300:
                continue

            generated = generate_short_description(name, description)
            products.append({
                "name": name,
                "price": float(price),
                "picture": picture,
                "url": url,
                "description": generated
            })

        return products

    except Exception as e:
        logger.error(f"Ошибка загрузки YML: {e}")
        return []
# Отправка товара в канал
async def post_product_to_channel(context: ContextTypes.DEFAULT_TYPE):
    global product_queue
    if not product_queue:
        product_queue = fetch_products_from_yml()
        if not product_queue:
            logger.warning("Нет товаров для публикации.")
            return

    product = product_queue.pop(0)

    caption = f"<b>{product['name']}</b>\n\n{product['description']}\n\nЦена: {int(product['price'])}₽"
    button = InlineKeyboardMarkup([[InlineKeyboardButton("Купить", url=product['url'])]])

    await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=product["picture"],
        caption=caption,
        parse_mode="HTML",
        reply_markup=button
    )

# Команды и обработчики
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен. Меню ниже:", reply_markup=menu)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    query = update.callback_query
    await query.answer()

    if query.data == "next":
        await post_product_to_channel(context)
    elif query.data == "pause":
        scheduler.pause()
        await query.edit_message_text("Публикации приостановлены.", reply_markup=menu)
    elif query.data == "resume":
        scheduler.resume()
        await query.edit_message_text("Публикации возобновлены.", reply_markup=menu)
    elif query.data == "queue":
        await query.edit_message_text(f"Товаров в очереди: {len(product_queue)}", reply_markup=menu)
    elif query.data == "log":
        try:
            with open("bot_log.txt", "r", encoding="utf-8") as f:
                log_content = f.readlines()[-10:]
            await query.edit_message_text("Последние записи:\n" + "".join(log_content), reply_markup=menu)
        except Exception as e:
            await query.edit_message_text(f"Ошибка чтения лога: {e}", reply_markup=menu)
    elif query.data == "status":
        is_paused = scheduler.state == 0
        await query.edit_message_text(f"Статус: {'⏸ Пауза' if is_paused else '▶️ Активен'}", reply_markup=menu)
    elif query.data == "skip":
        if product_queue:
            skipped = product_queue.pop(0)
            await query.edit_message_text(f"Товар «{skipped['name']}» пропущен.", reply_markup=menu)
        else:
            await query.edit_message_text("Очередь пуста.", reply_markup=menu)
# Отправка очереди постов
async def handle_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot_data["queue"]:
        queue_text = "\n\n".join(
            [f"{i+1}. {item['name']} – {item['price']}₽" for i, item in enumerate(context.bot_data["queue"][:10])]
        )
        await update.callback_query.message.reply_text(f"Очередь постов:\n\n{queue_text}", reply_markup=menu)
    else:
        await update.callback_query.message.reply_text("Очередь пуста.", reply_markup=menu)

# Отправка лога
async def handle_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with open("bot_log.txt", "r") as log_file:
            lines = log_file.readlines()[-30:]
            await update.callback_query.message.reply_text("Последние строки лога:\n\n" + "".join(lines), reply_markup=menu)
    except Exception as e:
        await update.callback_query.message.reply_text(f"Ошибка чтения лога: {e}", reply_markup=menu)

# Статистика
async def handle_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = len(context.bot_data.get("queue", []))
    status = "Активен" if context.bot_data.get("status") else "На паузе"
    await update.callback_query.message.reply_text(
        f"Статус бота: {status}\nТоваров в очереди: {total}",
        reply_markup=menu
    )

# Стартовая команда
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Доступ запрещен.")
        return
    await update.message.reply_text("Бот готов к работе!", reply_markup=menu)

# Главная функция запуска
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    context = application.bot_data
    context["queue"] = fetch_products_from_yml()
    context["status"] = True

    scheduler = AsyncIOScheduler()
    scheduler.add_job(post_product, CronTrigger(hour=12, minute=0), args=[context])
    scheduler.start()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_buttons))

    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
