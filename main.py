import logging
import os
import requests
import xml.etree.ElementTree as ET
import asyncio

from fastapi import FastAPI, Request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Настройки
WEBHOOK_URL       = os.getenv("WEBHOOK_URL")
BOT_TOKEN         = os.getenv("BOT_TOKEN")
YML_URL           = "https://cdn.mysitemapgenerator.com/shareapi/yml/16046306746_514"
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
CHANNEL_ID        = "@myttoy66"
ADMIN_ID          = 487591931

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    [InlineKeyboardButton("📢 Рассылка", callback_data="broadcast")],
    [InlineKeyboardButton("🧠 Нейросеть", callback_data="ai")]
])

def load_products_from_yml(yml_url):
    try:
        r = requests.get(yml_url)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        prods = []
        for offer in root.findall(".//offer"):
            price = offer.findtext("price")
            pic   = offer.findtext("picture")
            name  = offer.findtext("name")
            url   = offer.findtext("url")
            desc  = offer.findtext("description", "")
            if price and pic:
                try:
                    price_i = int(float(price))
                    if price_i >= 300:
                        prods.append({
                            "id": offer.attrib.get("id"),
                            "name": name,
                            "price": price_i,
                            "picture": pic,
                            "url": url,
                            "description": desc
                        })
                except ValueError:
                    continue
        global product_queue
        product_queue = prods
        logger.info(f"Загружено товаров: {len(prods)}")
    except Exception as e:
        logger.error(f"Ошибка загрузки YML: {e}")

def load_products_from_sources():
    load_products_from_yml(YML_URL)

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
                {"role": "user",   "content": prompt}
            ],
            "temperature": 1.0,
            "top_p": 0.9,
            "n": 1
        }
        resp = requests.post(
            "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            json=payload, headers=headers
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.warning(f"GigaChat error: {e}")
        return "Отличный выбор по хорошей цене!"

async def publish_next_product(bot):
    global paused, product_queue
    if paused or not product_queue:
        return
    p = product_queue.pop(0)
    text = (
        f"<b>{p['name']}</b>\n\n"
        f"{generate_description(p['name'], p.get('description',''))}\n\n"
        f"<b>{p['price']} ₽</b>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Купить", url=p['url'])]])
    try:
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=p['picture'],
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен.", reply_markup=main_menu)

async def pause(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = True
    await update.message.reply_text("Публикации приостановлены.", reply_markup=main_menu)

async def resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = False
    await update.message.reply_text("Публикации возобновлены.", reply_markup=main_menu)

async def next_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await publish_next_product(ctx.bot)

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    state = "⏸ Пауза" if paused else "▶️ Активен"
    await update.message.reply_text(f"Текущий статус: {state}", reply_markup=main_menu)

async def show_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(f"В очереди: {len(product_queue)} товаров.", reply_markup=main_menu)

async def broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Отправьте фото с подписью для рассылки в канал.", reply_markup=main_menu)

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if update.message.caption:
        photo_file = update.message.photo[-1].file_id
        try:
            await ctx.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo_file,
                caption=update.message.caption,
                parse_mode="HTML"
            )
            await update.message.reply_text("Сообщение отправлено в канал.", reply_markup=main_menu)
        except Exception as e:
            logger.error(f"Ошибка рассылки: {e}")
            await update.message.reply_text("Ошибка при отправке.", reply_markup=main_menu)

async def ask_ai(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        response = generate_description("Нейросеть", "Образец генерации описания")
        await update.message.reply_text(f"Ответ нейросети:\n\n{response}", reply_markup=main_menu)
    except Exception as e:
        logger.error(f"Ошибка нейросети: {e}")
        await update.message.reply_text("Ошибка генерации.", reply_markup=main_menu)

# Заглушка для menu_callback для обработки callback запросов
async def menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("next", next_cmd))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("queue", show_queue))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("log", status))
    application.add_handler(CommandHandler("ai", ask_ai))

    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(menu_callback))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(load_products_from_sources, "interval", hours=1)
    scheduler.add_job(lambda: asyncio.create_task(publish_next_product(application.bot)), "cron", hour=12, minute=0, timezone="Europe/Moscow")
    scheduler.start()

    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        webhook_url=f"{WEBHOOK_URL}"
    )

if __name__ == "__main__":
    main()