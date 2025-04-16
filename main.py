import logging
import os
import requests
import yaml
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes
from datetime import time
import base64

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 487591931
SITE_URL = "https://mytoy66.ru"
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

