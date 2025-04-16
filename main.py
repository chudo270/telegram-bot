import nest_asyncio
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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_log.txt'
)
logger = logging.getLogger(__name__)

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
# Генерация краткого описания с помощью OpenAI
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

# Загрузка товаров из YML
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
# Публикация товара в канал
async def post_product_to_channel(context: ContextTypes.DEFAULT_TYPE):
    queue = context.bot_data.get("queue", [])
    if not queue:
        logger.warning("Очередь пуста, пробуем загрузить заново.")
        queue = fetch_products_from_yml()
        context.bot_data["queue"] = queue
        if not queue:
            logger.error("Не удалось загрузить товары.")
            return

    product = queue.pop(0)

    caption = f"<b>{product['name']}</b>\n\n{product['description']}\n\nЦена: {int(product['price'])}₽"
    button = InlineKeyboardMarkup([[InlineKeyboardButton("Купить", url=product['url'])]])

    try:
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=product["picture"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=button
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке товара: {e}")

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Доступ запрещён.")
        return
    await update.message.reply_text("Бот запущен. Меню ниже:", reply_markup=menu)

# Обработка кнопок
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    query = update.callback_query
    await query.answer()

    data = query.data
    queue = context.bot_data.get("queue", [])

    if data == "next":
        await post_product_to_channel(context)
        await query.edit_message_text("Отправлен следующий товар.", reply_markup=menu)

    elif data == "pause":
        context.bot_data["paused"] = True
        await query.edit_message_text("Публикация поставлена на паузу.", reply_markup=menu)

    elif data == "resume":
        context.bot_data["paused"] = False
        await query.edit_message_text("Публикация возобновлена.", reply_markup=menu)

    elif data == "queue":
        text = "\n\n".join(
            [f"{i+1}. {item['name']} – {item['price']}₽" for i, item in enumerate(queue[:10])]
        ) if queue else "Очередь пуста."
        await query.edit_message_text(text, reply_markup=menu)

    elif data == "log":
        try:
            with open("bot_log.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()[-10:]
            await query.edit_message_text("Последние записи:\n" + "".join(lines), reply_markup=menu)
        except Exception as e:
            await query.edit_message_text(f"Ошибка чтения лога: {e}", reply_markup=menu)

    elif data == "status":
        paused = context.bot_data.get("paused", False)
        status = "⏸ Пауза" if paused else "▶️ Активен"
        await query.edit_message_text(f"Статус: {status}", reply_markup=menu)

    elif data == "skip":
        if queue:
            skipped = queue.pop(0)
            await query.edit_message_text(f"Пропущен: {skipped['name']}", reply_markup=menu)
        else:
            await query.edit_message_text("Очередь пуста.", reply_markup=menu)
# Главная функция запуска
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    context = application.bot_data

    # Начальная загрузка товаров
    context["queue"] = fetch_products_from_yml()
    context["paused"] = False

    # Планировщик публикаций
    scheduler = AsyncIOScheduler()

    def job_wrapper():
        if not context.get("paused", False):
            return asyncio.create_task(post_product_to_channel(context))
        else:
            logger.info("Публикация на паузе.")

    scheduler.add_job(job_wrapper, CronTrigger(hour=12, minute=0))
    scheduler.start()

    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_buttons))

    # Запуск бота
    await application.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    asyncio.run(main())
