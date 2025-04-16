import asyncio
import logging
import os
import requests
import yaml
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters  # <-- добавлен MessageHandler
)
from datetime import time
import base64
import uuid
import xml.etree.ElementTree as ET

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 487591931
SITE_URL = "https://myttoy66.ru"
YML_URL = "https://mytoy66.ru/integration?int=avito&name=avitoo"
GIGACHAT_TOKEN = os.getenv("GIGACHAT_TOKEN")

# Очередь товаров
product_queue = []
paused = False

# Меню
menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("▶️ Следующий", callback_data="next"),
     InlineKeyboardButton("⏸ Пауза", callback_data="pause"),
     InlineKeyboardButton("▶ Возобновить", callback_data="resume")],
    [InlineKeyboardButton("📊 Статус", callback_data="status"),
     InlineKeyboardButton("📦 Очередь", callback_data="queue")],
    [InlineKeyboardButton("📜 Лог", callback_data="log"),
     InlineKeyboardButton("⏭ Пропустить", callback_data="skip")],
    [InlineKeyboardButton("📢 Тест рассылки", callback_data="broadcast")]
])

# Старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен.", reply_markup=menu)

# Пауза
async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = True
    await update.message.reply_text("Публикация приостановлена.", reply_markup=menu)

# Возобновление
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = False
    await update.message.reply_text("Публикация возобновлена.", reply_markup=menu)
def generate_description(title: str, original_description: str = "") -> str:
    prompt = f"Придумай краткое продающее описание на русском для товара с названием '{title}'."
    if original_description:
        prompt += f" Описание товара: {original_description}"

    headers = {
        "Authorization": f"Bearer {GIGACHAT_TOKEN}",
        "Content-Type": "application/json"
    }
    json_data = {
        "model": "GigaChat-Pro",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 1.0
    }

    try:
        response = requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                                 headers=headers, json=json_data, timeout=10)
        response.raise_for_status()
        answer = response.json()
        return answer['choices'][0]['message']['content'].strip()
    except Exception as e:
        logging.error(f"Ошибка генерации описания: {e}")
        return "Отличный выбор для вас!"


async def post_next_product(context: ContextTypes.DEFAULT_TYPE):
    global product_queue, paused
    if paused or not product_queue:
        return

    product = product_queue.pop(0)
    if not product.get("picture") or not product.get("price") or int(product.get("price", 0)) < 300:
        return

    description = product.get("description", "")
    short_description = generate_description(product["name"], description)

    caption = f"<b>{product['name']}</b>\n\n{short_description}\n\n<b>Цена: {product['price']}₽</b>"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Купить", url=product['url'])
    ]])

    try:
        await context.bot.send_photo(
            chat_id="@your_channel_name",
            photo=product["picture"],
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка отправки товара: {e}")
def fetch_products():
    try:
        res = requests.get(YML_URL)
        res.raise_for_status()
        root = ET.fromstring(res.content)
        items = []
        for offer in root.findall(".//offer"):
            try:
                price = int(float(offer.findtext("price", "0")))
                picture = offer.findtext("picture")
                name = offer.findtext("name", "").strip()
                description = offer.findtext("description", "").strip()
                url = offer.findtext("url")
                vendor_code = offer.get("id")

                if not picture or price < 300 or not name:
                    continue

                items.append({
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "description": description,
                    "price": price,
                    "picture": picture,
                    "url": url,
                    "vendor_code": vendor_code
                })
            except Exception as e:
                logging.warning(f"Ошибка при обработке товара: {e}")
        return items
    except Exception as e:
        logging.error(f"Ошибка загрузки YML: {e}")
        return []


# Команды
async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await post_next_product(context)


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = True
    await update.message.reply_text("Публикация приостановлена.")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = False
    await update.message.reply_text("Публикация возобновлена.")


async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not product_queue:
        await update.message.reply_text("Очередь пуста.")
    else:
        preview = "\n".join([f"{i+1}. {p['name']}" for i, p in enumerate(product_queue[:10])])
        await update.message.reply_text(f"<b>Очередь:</b>\n{preview}", parse_mode="HTML")
async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Все логи приходят сюда автоматически.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    status = "⏸ Пауза" if paused else "▶️ Активен"
    await update.message.reply_text(f"<b>Статус:</b> {status}", parse_mode="HTML")


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if product_queue:
        skipped = product_queue.pop(0)
        await update.message.reply_text(f"Пропущен товар: {skipped['name']}")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Отправьте сообщение (с фото или без) для рассылки:")
    context.user_data["awaiting_broadcast"] = True


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if context.user_data.get("awaiting_broadcast"):
        context.user_data["awaiting_broadcast"] = False
        if update.message.photo:
            photo = update.message.photo[-1].file_id
            caption = update.message.caption or ""
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=caption)
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=update.message.text)
        await update.message.reply_text("Сообщение отправлено.")


async def post_next_product(context: ContextTypes.DEFAULT_TYPE):
    if not product_queue:
        return
    product = product_queue.pop(0)
    caption = generate_caption(product)
    try:
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=product["picture"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Купить", url=product["url"])]]),
        )
        logging.info(f"Опубликован: {product['name']}")
    except Exception as e:
        logging.error(f"Ошибка публикации: {e}")


async def scheduled_post(context: ContextTypes.DEFAULT_TYPE):
    if not paused and product_queue:
        await post_next_product(context)


async def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("log", cmd_log))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(MessageHandler(filters.ALL, handle_broadcast))

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(scheduled_post, CronTrigger(hour=12, minute=0))
    scheduler.start()

    logging.info("Бот запущен.")
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()
    
import asyncio

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(start_bot())

