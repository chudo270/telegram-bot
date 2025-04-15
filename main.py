import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import asyncio

# Конфигурация
BOT_TOKEN = '7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0'
ADMIN_ID = 487591931

# Включение логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Глобальные переменные
posting_paused = False
current_product_index = 0
products_cache = [
    {'title': 'Товар 1', 'price': 350, 'description': 'Описание товара 1', 'photo': 'https://example.com/img1.jpg'},
    {'title': 'Товар 2', 'price': 500, 'description': 'Описание товара 2', 'photo': 'https://example.com/img2.jpg'}
    # Здесь можно подключить реальный источник данных
]

# Команды администратора
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен. Используйте /next, /pause, /resume, /status, /log.")

async def next_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await post_next_product(context)

async def pause_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global posting_paused
    if update.effective_user.id != ADMIN_ID:
        return
    posting_paused = True
    await update.message.reply_text("Публикация приостановлена.")

async def resume_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global posting_paused
    if update.effective_user.id != ADMIN_ID:
        return
    posting_paused = False
    await update.message.reply_text("Публикация возобновлена.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    status = "приостановлена" if posting_paused else "активна"
    await update.message.reply_text(f"Публикация сейчас {status}. Текущий индекс товара: {current_product_index}")

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Лог пуст (или подключите лог-файл).")

# Функция публикации товара
async def post_next_product(context: ContextTypes.DEFAULT_TYPE):
    global current_product_index
    if posting_paused:
        return

    if current_product_index >= len(products_cache):
        current_product_index = 0

    product = products_cache[current_product_index]
    current_product_index += 1

    message = f"<b>{product['title']}</b>\nЦена: {product['price']}₽\n\n{product['description']}"
    keyboard = [[InlineKeyboardButton("Купить", url="https://example.com")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=product['photo'],
        caption=message,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# Планировщик ежедневной публикации
async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    await post_next_product(context)

# Основной запуск
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("next", next_post))
    application.add_handler(CommandHandler("pause", pause_posting))
    application.add_handler(CommandHandler("resume", resume_posting))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("log", log))

    # Планируем ежедневную публикацию в 12:00 МСК
    application.job_queue.run_daily(daily_post, time=datetime.time(hour=12, minute=0, tzinfo=datetime.timezone.utc))

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await application.updater.idle()

if __name__ == '__main__':
    import datetime
    asyncio.run(main())
