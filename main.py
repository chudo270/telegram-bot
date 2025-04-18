import logging
import os
import requests
import xml.etree.ElementTree as ET
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ====== Настройки ======
BOT_TOKEN         = os.getenv("BOT_TOKEN")
YML_URL           = "https://cdn.mysitemapgenerator.com/shareapi/yml/16046306746_514"
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
CHANNEL_ID        = "@myttoy66"
ADMIN_ID          = 487591931

# ====== Логирование ======
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== Глобальные переменные ======
product_queue = []
paused = False

main_menu = InlineKeyboardMarkup([
    [InlineKeyboardButton("▶️ Следующий",   callback_data="next")],
    [InlineKeyboardButton("⏸ Пауза",        callback_data="pause"),
     InlineKeyboardButton("▶️ Возобновить", callback_data="resume")],
    [InlineKeyboardButton("📦 Очередь",      callback_data="queue"),
     InlineKeyboardButton("⏭ Пропустить",   callback_data="skip")],
    [InlineKeyboardButton("📊 Статус",       callback_data="status"),
     InlineKeyboardButton("📝 Логи",         callback_data="log")],
    [InlineKeyboardButton("📢 Рассылка",     callback_data="broadcast")],
    [InlineKeyboardButton("🧠 Нейросеть",    callback_data="ai")]
])

# ====== Функции загрузки товаров ======
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
                            "id":          offer.attrib.get("id"),
                            "name":        name,
                            "price":       price_i,
                            "picture":     pic,
                            "url":         url,
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

# ====== Генерация продающего описания ======
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
            "top_p":       0.9,
            "n":           1
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
        # ====== Публикация товара ======
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

# ====== Handlers для команд и кнопок ======
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен.", reply_markup=main_menu)

async def pause_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = True
    if update.callback_query:
        await update.callback_query.answer("Публикации приостановлены.")
    else:
        await update.message.reply_text("Публикации приостановлены.", reply_markup=main_menu)

async def resume_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = False
    if update.callback_query:
        await update.callback_query.answer("Публикации возобновлены.")
    else:
        await update.message.reply_text("Публикации возобновлены.", reply_markup=main_menu)

async def next_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if update.callback_query:
        await update.callback_query.answer()
    await publish_next_product(ctx.bot)

async def show_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = f"В очереди: {len(product_queue)} товаров."
    if update.callback_query:
        await update.callback_query.answer(text)
    else:
        await update.message.reply_text(text, reply_markup=main_menu)

async def show_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        with open("bot.log", "r") as log_file:
            logs = ''.join(log_file.readlines()[-10:])
        if update.callback_query:
            await update.callback_query.answer()
            await ctx.bot.send_message(chat_id=update.effective_user.id, text=f"Последние логи:\n{logs}")
        else:
            await update.message.reply_text(f"Последние логи:\n{logs}", reply_markup=main_menu)
    except Exception as e:
        logger.error(f"Ошибка чтения логов: {e}")
        if update.callback_query:
            await update.callback_query.answer("Не удалось загрузить логи.")
        else:
            await update.message.reply_text("Не удалось загрузить логи.", reply_markup=main_menu)

async def broadcast_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = update.message.text.replace("/broadcast", "").strip()
    if not text:
        await update.message.reply_text("Введите текст после /broadcast", reply_markup=main_menu)
        return
    try:
        await ctx.bot.send_message(chat_id=CHANNEL_ID, text=text)
        await update.message.reply_text("Рассылка отправлена!", reply_markup=main_menu)
    except Exception as e:
        logger.error(f"Ошибка рассылки: {e}")
        await update.message.reply_text("Ошибка при рассылке.", reply_markup=main_menu)

async def skip_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.callback_query.answer("Пропускаем товар…")
    await publish_next_product(ctx.bot)

async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    status = "⏸ Приостановлено" if paused else "▶️ Активно"
    await update.callback_query.answer(f"Статус бота: {status}", show_alert=True)

async def ai_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.callback_query.answer("Нейросеть пока не реализована", show_alert=True)

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # — CommandHandlers
    application.add_handler(CommandHandler("start",     start))
    application.add_handler(CommandHandler("pause",     pause_cmd))
    application.add_handler(CommandHandler("resume",    resume_cmd))
    application.add_handler(CommandHandler("next",      next_cmd))
    application.add_handler(CommandHandler("queue",     show_queue))
    application.add_handler(CommandHandler("log",       show_logs))
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))

    # — CallbackQueryHandlers
    application.add_handler(CallbackQueryHandler(pause_cmd,     pattern="^pause$"))
    application.add_handler(CallbackQueryHandler(resume_cmd,    pattern="^resume$"))
    application.add_handler(CallbackQueryHandler(next_cmd,      pattern="^next$"))
    application.add_handler(CallbackQueryHandler(skip_cmd,      pattern="^skip$"))
    application.add_handler(CallbackQueryHandler(show_queue,    pattern="^queue$"))
    application.add_handler(CallbackQueryHandler(show_logs,     pattern="^log$"))
    application.add_handler(CallbackQueryHandler(broadcast_cmd, pattern="^broadcast$"))
    application.add_handler(CallbackQueryHandler(status_cmd,    pattern="^status$"))
    application.add_handler(CallbackQueryHandler(ai_cmd,        pattern="^ai$"))

    # — Scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(load_products_from_sources, "interval", hours=1)
    scheduler.add_job(
        lambda: asyncio.create_task(publish_next_product(application.bot)),
        "cron", hour=12, minute=0, timezone="Europe/Moscow"
    )
    scheduler.start()

    # — Запуск polling + сброс старого webhook
    application.run_polling().

if __name__ == "__main__":
    main()