import logging
import os
import requests
import xml.etree.ElementTree as ET # заменяет yaml
import nest_asyncio
nest_asyncio.apply()
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from datetime import time
import base64
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 487591931
SITE_URL = "https://myttoy66.ru"
YML_URL = "https://cdn.mysitemapgenerator.com/shareapi/yml/16046306746_514"
GIGACHAT_TOKEN = os.getenv("GIGACHAT_TOKEN")

product_queue = []
paused = False

main_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("▶️ Следующий", callback_data="next")],
    [InlineKeyboardButton("⏸ Пауза", callback_data="pause"),
     InlineKeyboardButton("▶️ Возобновить", callback_data="resume")],
    [InlineKeyboardButton("📦 Очередь", callback_data="queue"),
     InlineKeyboardButton("⏭ Пропустить", callback_data="skip")],
    [InlineKeyboardButton("📊 Статус", callback_data="status"),
     InlineKeyboardButton("📝 Логи", callback_data="log")],
    [InlineKeyboardButton("📢 Рассылка", callback_data="broadcast")]
])

import xml.etree.ElementTree as ET

def load_products_from_yml(yml_url):
    try:
        response = requests.get(yml_url)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            products = []

            # Путь к тегу <offer> внутри <offers>
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


def generate_description(name, description):
    try:
        prompt = f"Сделай короткое продающее описание товара по названию: {name}"
        if description:
            prompt += f" и описанию: {description}"

        headers = {
            "Authorization": f"Bearer {GIGACHAT_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "GigaChat-Pro",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 1.0,
            "max_tokens": 100
        }
        response = requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                                 headers=headers, json=data)
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        logging.error(f"Ошибка генерации описания: {e}")
    return "Отличный выбор по хорошей цене!"

async def post_product_to_channel(bot, product):
    title = f"<b>{product['name']}</b>"
    price = f"<b>{product['price']}₽</b>"
    url = product['url']
    description = generate_description(product['name'], product.get("description", ""))

    caption = f"{title}\n\n{description}\n\nЦена: {price}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Купить", url=url)]])

    await bot.send_photo(chat_id='@myttoy66', photo=product["picture"], caption=caption, parse_mode="HTML", reply_markup=reply_markup)

async def publish_scheduled(context: ContextTypes.DEFAULT_TYPE):
    global paused, product_queue
    if not paused and product_queue:
        product = product_queue.pop(0)
        await post_product_to_channel(context.bot, product)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused, product_queue
    if update.effective_user.id != ADMIN_ID:
        return

    query = update.callback_query
    await query.answer()

    if query.data == "next":
        if product_queue:
            product = product_queue.pop(0)
            await post_product_to_channel(context.bot, product)
        else:
            await query.edit_message_text("Очередь пуста.", reply_markup=main_menu)

    elif query.data == "pause":
        paused = True
        await query.edit_message_text("Публикация приостановлена.", reply_markup=main_menu)

    elif query.data == "resume":
        paused = False
        await query.edit_message_text("Публикация возобновлена.", reply_markup=main_menu)

    elif query.data == "queue":
        await query.edit_message_text(f"Товаров в очереди: {len(product_queue)}", reply_markup=main_menu)

    elif query.data == "status":
        status = "Пауза" if paused else "Активен"
        await query.edit_message_text(f"Статус: {status}", reply_markup=main_menu)

    elif query.data == "log":
        await query.edit_message_text("Логов нет — всё работает нормально.", reply_markup=main_menu)

    elif query.data == "skip":
        if product_queue:
            skipped = product_queue.pop(0)
            await query.edit_message_text(f"Пропущен: {skipped['name']}", reply_markup=main_menu)
        else:
            await query.edit_message_text("Очередь пуста.", reply_markup=main_menu)

    elif query.data == "broadcast":
        await query.edit_message_text("Отправь сообщение (или фото с подписью) для рассылки.", reply_markup=None)
        context.user_data["broadcast"] = True

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not context.user_data.get("broadcast"):
        return

    context.user_data["broadcast"] = False

    if update.message.photo:
        photo = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        await context.bot.send_photo(chat_id="@myttoy66", photo=photo, caption=caption)
    elif update.message.text:
        await context.bot.send_message(chat_id="@myttoy66", text=update.message.text)

    await update.message.reply_text("Сообщение отправлено в канал.", reply_markup=main_menu)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("Панель управления:", reply_markup=main_menu)

async def start_bot():
    global product_queue
    product_queue = load_products_from_yml(YML_URL)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.ALL, handle_broadcast))

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(publish_scheduled, 'cron', hour=12, minute=0, args=[app.bot])
    scheduler.start()

    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_bot())
