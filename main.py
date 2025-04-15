import nest_asyncio
nest_asyncio.apply()

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from bs4 import BeautifulSoup
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = '7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0'
CHANNEL_ID = '@mytoy66'
ADMIN_ID = 487591931

product_queue = []
paused = False
write_mode = {}

URL = "https://mytoy66.ru/group?type=latest"

async def fetch_products():
    global product_queue
    async with aiohttp.ClientSession() as session:
        async with session.get(URL) as response:
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            items = soup.select('.product-item')
            queue = []
            for item in items:
                title = item.select_one('.product-title')
                img = item.select_one('img')
                price = item.select_one('.price')
                link = item.select_one('a')

                if not (title and img and price and link):
                    continue

                queue.append({
                    'name': title.get_text(strip=True),
                    'image': img['src'],
                    'price': price.get_text(strip=True),
                    'url': 'https://mytoy66.ru' + link['href']
                })
            product_queue = queue

def build_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Следующий", callback_data="next")],
        [InlineKeyboardButton("⏸ Пауза" if not paused else "▶️ Возобновить", callback_data="pause")],
        [InlineKeyboardButton("✏️ Написать", callback_data="write")]
    ])

async def send_product(context: CallbackContext):
    global product_queue
    if paused or not product_queue:
        return
    product = product_queue.pop(0)
    text = f"<b>{product['name']}</b>\nЦена: {product['price']}\n<a href='{product['url']}'>Смотреть товар</a>"
    await context.bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=product['image'],
        caption=text,
        parse_mode='HTML',
        reply_markup=build_keyboard()
    )

async def start(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен", reply_markup=build_keyboard())

async def handle_callback(update: Update, context: CallbackContext):
    global paused
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.edit_message_reply_markup()
        return

    if query.data == "next":
        await send_product(context)
    elif query.data == "pause":
        paused = not paused
        await query.edit_message_reply_markup(reply_markup=build_keyboard())
    elif query.data == "write":
        write_mode[query.from_user.id] = True
        await query.message.reply_text("Введите текст, который хотите отправить в канал:")

async def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if write_mode.get(user_id):
        text = update.message.text
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text)
        write_mode[user_id] = False
        await update.message.reply_text("Сообщение отправлено.")
    else:
        await update.message.reply_text("Для управления используйте кнопки.")

async def main():
    await fetch_products()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: asyncio.create_task(send_product(app.bot)), 'interval', minutes=60)
    scheduler.start()

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
