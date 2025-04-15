import logging
import os
import random
import requests
import feedparser
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackContext, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

TOKEN = "7766369540:AAGKLs-BDwavHlN6dr9AUHWIeIhdJLq5nM0"
CHANNEL_ID = "@Myttoy66"
ADMIN_ID = 487591931

MAIN_SOURCE = "https://mytoy66.ru/group?type=latest"
RESERVE_YML = "https://mytoy66.ru/integration?int=avito&name=avitoo"

used_links = set()

def get_products_from_site():
    try:
        response = requests.get(MAIN_SOURCE, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        products = soup.find_all("div", class_="product-card")
        results = []

        for product in products:
            link_tag = product.find("a", href=True)
            if not link_tag:
                continue

            url = "https://mytoy66.ru" + link_tag["href"]
            if url in used_links:
                continue

            image_tag = product.find("img")
            if not image_tag or "src" not in image_tag.attrs:
                continue
            image_url = image_tag["src"]

            title_tag = product.find("div", class_="product-card-title")
            title = title_tag.text.strip() if title_tag else "Товар"

            price_tag = product.find("span", class_="price")
            price_text = price_tag.text.strip() if price_tag else ""
            price = int("".join(filter(str.isdigit, price_text))) if price_text else 0

            if price < 300:
                continue

            buy_button = product.find("a", class_="buy-btn")
            buy_url = "https://mytoy66.ru" + buy_button["href"] if buy_button else url

            description = product.find("div", class_="product-card-description")
            if description:
                description_text = description.text.strip()
            else:
                description_text = f"{title} — отличный товар, который подойдёт вам по качеству и цене!"

            results.append({
                "title": title,
                "price": price,
                "image": image_url,
                "url": buy_url,
                "desc": description_text
            })

        return results
    except Exception as e:
        logging.error(f"Ошибка при парсинге основного сайта: {e}")
        return []

def get_product_from_yml():
    try:
        feed = feedparser.parse(RESERVE_YML)
        for entry in feed.entries:
            if 'image_link' not in entry or not entry.image_link:
                continue

            price = int(float(entry.get("price", 0)))
            if price < 300:
                continue

            return {
                "title": entry.title,
                "price": price,
                "image": entry.image_link,
                "url": entry.link,
                "desc": entry.get("description", "Отличный товар!")
            }
    except Exception as e:
        logging.error(f"Ошибка при парсинге YML: {e}")
    return None

async def post_product(context: CallbackContext):
    bot = context.bot
    product = None

    products = get_products_from_site()
    random.shuffle(products)

    for p in products:
        if p["url"] not in used_links:
            product = p
            used_links.add(p["url"])
            break

    if not product:
        product = get_product_from_yml()
        if not product:
            logging.warning("Нет товаров для публикации")
            return

    caption = f"<b>{product['title']}</b>\nЦена: {product['price']}₽\n\n{product['desc']}"
    buttons = [[InlineKeyboardButton("Купить", url=product["url"])]]
    reply_markup = InlineKeyboardMarkup(buttons)

    try:
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=product["image"],
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        logging.info(f"Опубликован товар: {product['title']}")
    except Exception as e:
        logging.error(f"Ошибка отправки поста: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("Бот готов к работе.")
    else:
        await update.message.reply_text("У вас нет прав для управления ботом.")

async def next_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await post_product(context)
    else:
        await update.message.reply_text("Доступ запрещён.")

if __name__ == "__main__":
    import asyncio

    async def main():
        application = Application.builder().token(TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("next", next_post))

        scheduler = AsyncIOScheduler()
        scheduler.add_job(post_product, CronTrigger(hour=12, minute=0))
        scheduler.start()

        PORT = int(os.environ.get("PORT", 8443))
        await application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"https://worker-production-c8d5.up.railway.app/{TOKEN}"
        )

    asyncio.run(main())
