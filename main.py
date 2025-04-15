import logging
import asyncio
import json
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import os

TOKEN = "7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0"
ADMIN_ID = 487591931
CHANNEL_ID = "@myttoy66"
POST_TIME = "12:00"
MAIN_SOURCE = "https://mytoy66.ru/group?type=latest"
RESERVE_SOURCE = "https://mytoy66.ru/integration?int=avito&name=avitoo"

application = Application.builder().token(TOKEN).build()
scheduler = AsyncIOScheduler()

paused = False
last_posted = set()


def get_products_from_main():
    try:
        response = requests.get(MAIN_SOURCE)
        response.raise_for_status()
        data = response.json()
        return data.get("products", [])
    except Exception as e:
        logging.error(f"Ошибка при получении с основного источника: {e}")
        return []


def get_products_from_reserve():
    try:
        response = requests.get(RESERVE_SOURCE)
        response.raise_for_status()
        from xml.etree import ElementTree as ET
        tree = ET.fromstring(response.content)
        products = []
        for offer in tree.findall(".//offer"):
            product = {
                "name": offer.findtext("name"),
                "price": float(offer.findtext("price", "0")),
                "description": offer.findtext("description", ""),
                "picture": offer.findtext("picture"),
                "url": offer.findtext("url"),
            }
            products.append(product)
        return products
    except Exception as e:
        logging.error(f"Ошибка при разборе YML: {e}")
        return []


def generate_description(product):
    if product.get("description"):
        return product["description"]
    return f"{product['name']} — отличный товар по выгодной цене!"


async def post_product():
    global paused, last_posted
    if paused:
        logging.info("Публикация приостановлена.")
        return

    products = get_products_from_main()
    if not products:
        products = get_products_from_reserve()

    for product in products:
        if isinstance(product, dict):
            name = product.get("name", "")
            price = float(product.get("price", 0))
            photo = product.get("image") or product.get("picture")
            desc = generate_description(product)
            link = product.get("url", "")

            if not name or not photo or price < 300 or name in last_posted:
                continue

            caption = f"<b>{name}</b>\n\n{desc}\n\nЦена: {price}₽"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Купить", url=link)]]) if link else None

            try:
                await application.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=photo,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                last_posted.add(name)
                logging.info(f"Опубликован товар: {name}")
                return
            except Exception as e:
                logging.error(f"Ошибка при отправке товара: {e}")

    logging.info("Нет подходящих товаров для публикации.")


# Команды управления

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Бот запущен. Используй /next, /pause, /resume, /status, /log")


async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await post_product()
    await update.message.reply_text("Следующий товар опубликован.")


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = True
    await update.message.reply_text("Автопостинг приостановлен.")


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused
    if update.effective_user.id != ADMIN_ID:
        return
    paused = False
    await update.message.reply_text("Автопостинг возобновлён.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    status = "приостановлен" if paused else "активен"
    await update.message.reply_text(f"Состояние автопостинга: {status}")


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(f"Последние опубликованные товары:\n" + "\n".join(last_posted) if last_posted else "Пока ничего не опубликовано.")


def schedule_posts():
    hour, minute = map(int, POST_TIME.split(":"))
    scheduler.add_job(post_product, 'cron', hour=hour, minute=minute)
    scheduler.start()


def set_commands():
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("next", "Опубликовать следующий товар"),
        BotCommand("pause", "Приостановить автопостинг"),
        BotCommand("resume", "Возобновить автопостинг"),
        BotCommand("status", "Проверить статус"),
        BotCommand("log", "Показать лог публикаций"),
    ]
    asyncio.run(application.bot.set_my_commands(commands))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("next", next_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("log", log_command))

    schedule_posts()
    set_commands()

    application.run_polling()
