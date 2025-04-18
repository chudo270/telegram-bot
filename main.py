import logging
import os
import requests
import xml.etree.ElementTree as ET
import asyncio
import datetime
from pytz import timezone
from aiohttp import web

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ====== Настройки ======
BOT_TOKEN         = os.getenv("BOT_TOKEN")
YML_URL           = "https://cdn.mysitemapgenerator.com/shareapi/yml/16046306746_514"
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
CHANNEL_ID        = "@myttoy66"
ADMIN_ID          = 487591931

POST_TIME_HOUR = 12
POST_TIME_MINUTE = 0
ZONE = timezone("Europe/Moscow")

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

# ====== Загрузка товаров из YML ======
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

# ====== Генерация описания ======
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

# ====== Публикация ======
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

# ====== Декоратор ======
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("Доступ запрещён.")
            return
        return await func(update, context)
    return wrapper

# ====== Команды ======
@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("▶️ next"), KeyboardButton("⏸ pause"), KeyboardButton("▶ resume")],
        [KeyboardButton("📋 queue"), KeyboardButton("📤 broadcast")],
        [KeyboardButton("🧠 нейросеть"), KeyboardButton("🪵 log")],
        [KeyboardButton("ℹ️ status"), KeyboardButton("⏭ skip")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Меню управления ботом:", reply_markup=reply_markup)

@admin_only
async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await publish_next_product(context.bot)
    await update.message.reply_text("Следующий товар опубликован.")

@admin_only
async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    paused = True
    await update.message.reply_text("Автопубликация приостановлена.")

@admin_only
async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    paused = False
    await update.message.reply_text("Автопубликация возобновлена.")

@admin_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "Пауза" if paused else "Активен"
    await update.message.reply_text(f"Статус: {status}\nОчередь: {len(product_queue)} товаров")

@admin_only
async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Журнал логов недоступен — отправка только в Telegram.")

@admin_only
async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not product_queue:
        await update.message.reply_text("Очередь пуста.")
        return
    preview = "\n".join([f"{i+1}. {p['name']}" for i, p in enumerate(product_queue[:10])])
    await update.message.reply_text(f"Очередь товаров:\n\n{preview}")

@admin_only
async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if product_queue:
        skipped = product_queue.pop(0)
        await update.message.reply_text(f"Пропущен: {skipped['name']}")
    else:
        await update.message.reply_text("Очередь пуста.")

@admin_only
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        caption = update.message.caption or ""
        photo = update.message.photo[-1].file_id
        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=caption)
    elif update.message.text:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=update.message.text)
    await update.message.reply_text("Сообщение отправлено в канал.")

@admin_only
async def cmd_neuro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = generate_description("Игрушечный робот", "Многофункциональный робот с пультом ДУ")
    await update.message.reply_text(f"Ответ от нейросети:\n\n{text}")

# ====== Инициализация ======
async def initialize_product_queue():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, load_products_from_sources)

# ====== MAIN с вебхуком ======
async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.Regex("^▶️ next$"), cmd_next))
    app.add_handler(MessageHandler(filters.Regex("^⏸ pause$"), cmd_pause))
    app.add_handler(MessageHandler(filters.Regex("^▶ resume$"), cmd_resume))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ status$"), cmd_status))
    app.add_handler(MessageHandler(filters.Regex("^🪵 log$"), cmd_log))
    app.add_handler(MessageHandler(filters.Regex("^📋 queue$"), cmd_queue))
    app.add_handler(MessageHandler(filters.Regex("^⏭ skip$"), cmd_skip))
    app.add_handler(MessageHandler(filters.Regex("^📤 broadcast$"), cmd_broadcast))
    app.add_handler(MessageHandler(filters.Regex("^🧠 нейросеть$"), cmd_neuro))

    await initialize_product_queue()

    # webhook URL
    webhook_url = "https://worker-production-c8d5.up.railway.app/webhook"
    await app.bot.set_webhook(url=webhook_url)

    # AIOHTTP сервер
    async def handle(request):
        request_data = await request.json()
        update = Update.de_json(request_data, app.bot)
        await app.process_update(update)
        return web.Response()

    app_ = web.Application()
    app_.router.add_post("/webhook", handle)

    runner = web.AppRunner(app_)
    await runner.setup()

    PORT = int(os.getenv("PORT", 8443))
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print(f"Webhook запущен на {webhook_url}")

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())