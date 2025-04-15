import logging
import os
import random
import re
import time
from datetime import datetime
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
BOT_TOKEN = "7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0"
ADMIN_ID = 487591931
CHANNEL_ID = "@Myttoy66"
MAIN_SOURCE = "https://mytoy66.ru/group?type=latest"
YML_SOURCE = "https://mytoy66.ru/integration?int=avito&name=avitoo"

# Состояние
paused = False
products_cache = []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен и работает.")


async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Нет доступа.")
        return
    await update.message.reply_text("В логе пока всё чисто.")


def get_products_from_source(url):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return []

        products = response.json().get("products", [])
        filtered = []
        for product in products:
            if (
                product.get("price", 0) >= 300
                and product.get("image")
                and (product.get("description") or product.get("name"))
            ):
                filtered.append(product)
        return filtered
    except Exception as e:
        logger.error(f"Ошибка получения товаров: {e}")
        return []


def generate_description(name):
    return f"Интересный товар: {name}"


async def post_product(context: ContextTypes.DEFAULT_TYPE):
    global paused, products_cache

    if paused:
        return

    if not products_cache:
        products_cache = get_products_from_source(MAIN_SOURCE)
        if not products_cache:
            products_cache = get_products_from_source(YML_SOURCE)

    if not products_cache:
        logger.info("Нет подходящих товаров для публикации.")
        return

    product = products_cache.pop(0)
    name = product.get("name", "Без названия")
    description = product.get("description") or generate_description(name)
    price = product.get("price", 0)
    image = product.get("image")
    link = product.get("link", MAIN_SOURCE)

    caption = f"<b>{name}</b>\n\n{description}\n\nЦена: {price}₽\n<a href='{link}'>Подробнее</a>"

    keyboard = [
        [InlineKeyboardButton("Перейти в магазин", url=link)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=image,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
    except Exception as e:
        logger.error(f"Ошибка при публикации товара: {e}")


async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await post_product(context)


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id == ADMIN_ID:
        paused = True
        await update.message.reply_text("Публикации приостановлены.")


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id == ADMIN_ID:
        paused = False
        await update.message.reply_text("Публикации возобновлены.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    status = "Приостановлен" if paused else "Работает"
    await update.message.reply_text(f"Бот: {status}\nТоваров в очереди: {len(products_cache)}")


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("log", log))
    application.add_handler(CommandHandler("next", next_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("status", status_command))

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(post_product, CronTrigger(hour=12, minute=0), args=[application.bot])
    scheduler.start()

    application.run_polling()


if __name__ == "__main__":
    main()
