import logging
import os
import requests
import xml.etree.ElementTree as ET
from datetime import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Настройки из окружения
WEBHOOK_URL       = os.getenv("WEBHOOK_URL")       # e.g. https://worker-production-c8d5.up.railway.app
BOT_TOKEN         = os.getenv("BOT_TOKEN")
YML_URL           = "https://cdn.mysitemapgenerator.com/shareapi/yml/16046306746_514"
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
CHANNEL_ID        = "@myttoy66"
ADMIN_ID          = 487591931

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояние
product_queue = []
paused = False

main_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("▶️ Следующий",   callback_data="next")],
    [InlineKeyboardButton("⏸ Пауза",        callback_data="pause"),
     InlineKeyboardButton("▶️ Возобновить", callback_data="resume")],
    [InlineKeyboardButton("📦 Очередь",      callback_data="queue"),
     InlineKeyboardButton("⏭ Пропустить",   callback_data="skip")],
    [InlineKeyboardButton("📊 Статус",       callback_data="status"),
     InlineKeyboardButton("📝 Логи",        callback_data="log")],
    [InlineKeyboardButton("📢 Рассылка",     callback_data="broadcast")],
    [InlineKeyboardButton("🧠 Нейросеть",    callback_data="ai")]
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
                    pass
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

async def publish_next_product(ctx: ContextTypes.DEFAULT_TYPE):
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
        await ctx.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=p['picture'],
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")

# Команды и коллбэки
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
    await publish_next_product(ctx)

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    state = "⏸ Пауза" if paused else "▶️ Активен"
    await update.message.reply_text(f"Текущий статус: {state}", reply_markup=main_menu)

async def show_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(f"В очереди: {len(product_queue)} товаров.", reply_markup=main_menu)

async def broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    ctx.user_data["broadcast"] = True
    await update.message.reply_text("Пришлите текст или фото с подписью для рассылки.")

async def broadcast_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not ctx.user_data.get("broadcast"):
        return
    ctx.user_data["broadcast"] = False
    if update.message.photo:
        photo   = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        await ctx.bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=caption)
    else:
        await ctx.bot.send_message(chat_id=CHANNEL_ID, text=update.message.text)

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    data = q.data
    if data == "next":
        await publish_next_product(ctx)
    elif data == "pause":
        await pause(update, ctx)
    elif data == "resume":
        await resume(update, ctx)
    elif data == "queue":
        await show_queue(update, ctx)
    elif data == "status":
        await status(update, ctx)
    elif data == "broadcast":
        await broadcast_start(update, ctx)
    elif data == "skip":
        if product_queue:
            skipped = product_queue.pop(0)
            await q.edit_message_text(f"Пропущен: {skipped['name']}", reply_markup=main_menu)
        else:
            await q.edit_message_text("Очередь пуста.", reply_markup=main_menu)

def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("pause",    pause))
    app.add_handler(CommandHandler("resume",   resume))
    app.add_handler(CommandHandler("next",     next_cmd))
    app.add_handler(CommandHandler("status",   status))
    app.add_handler(CommandHandler("queue",    show_queue))
    app.add_handler(CommandHandler("broadcast",broadcast_start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    return app

def start_scheduler(app):
    sched = AsyncIOScheduler()
    sched.add_job(
        lambda: app.create_task(publish_next_product(app)),
        trigger='cron',
        hour=12,
        minute=0,
        timezone='Europe/Moscow'
    )
    sched.start()

def main():
    if not BOT_TOKEN or not WEBHOOK_URL:
        logger.error("BOT_TOKEN и WEBHOOK_URL должны быть заданы в окружении")
        return

    app = build_application()
    load_products_from_sources()
    start_scheduler(app)
    logger.info("Бот запущен и готов к работе.")

    PORT = int(os.getenv("PORT", "8080"))
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=f"/{BOT_TOKEN}",
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
