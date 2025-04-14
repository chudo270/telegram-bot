import telebot
import requests
import time
import random
from datetime import datetime
import schedule
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

TOKEN = "7891783737:AAGYR-iEqMO6ZlT3wIJdOTtx94Yb0jFLj20"
CHANNEL_ID = "@mytoy_test"
ADMIN_ID = 69033573
bot = telebot.TeleBot(TOKEN)

POST_HOUR = 12
MIN_PRICE = 300
FALLBACK_YML_URL = "https://mytoy66.ru/integration?int=avito&name=avitoo"

paused = False
used_products = []

def fetch_products():
    try:
        response = requests.get("https://mytoy66.ru")
        soup = BeautifulSoup(response.text, "html.parser")
        products = []

        for item in soup.select(".product-card"):
            title = item.select_one(".product-card-title")
            price = item.select_one(".product-card-price")
            img = item.select_one("img")
            link = item.select_one("a")

            if not (title and price and img and link):
                continue

            title_text = title.text.strip()
            price_text = price.text.strip().replace("₽", "").replace(" ", "")
            image_url = img["src"]
            product_url = link["href"]

            if not title_text or not price_text or not image_url:
                continue

            try:
                price_val = int(price_text)
            except ValueError:
                continue

            if price_val < MIN_PRICE:
                continue

            products.append({
                "title": title_text,
                "price": price_val,
                "image": image_url,
                "url": product_url
            })

        return products
    except Exception as e:
        print(f"Ошибка при получении товаров с сайта: {e}")
        return []

def fetch_yml_products():
    try:
        response = requests.get(FALLBACK_YML_URL)
        products = []
        root = ET.fromstring(response.content)
        for offer in root.findall(".//offer"):
            name = offer.find("name").text if offer.find("name") is not None else None
            price = offer.find("price").text if offer.find("price") is not None else None
            picture = offer.find("picture").text if offer.find("picture") is not None else None
            url = offer.find("url").text if offer.find("url") is not None else None

            if not name or not price or not picture or not url:
                continue

            try:
                price_val = int(float(price))
            except ValueError:
                continue

            if price_val < MIN_PRICE:
                continue

            products.append({
                "title": name,
                "price": price_val,
                "image": picture,
                "url": url
            })
        return products
    except Exception as e:
        print(f"Ошибка при получении товаров из YML: {e}")
        return []

def generate_caption(product):
    return f"{product['title']}"

Цена: {product['price']}₽
Ссылка: {product['url']}"

def publish_product():
    global used_products
    if paused:
        print("Бот на паузе, публикация отменена")
        return

    products = fetch_products()
    if not products:
        print("Основной сайт не дал товаров, используем YML")
        products = fetch_yml_products()

    products = [p for p in products if p["url"] not in used_products]

    if not products:
        print("Нет новых товаров для публикации")
        return

    product = random.choice(products)
    used_products.append(product["url"])

    try:
        bot.send_photo(CHANNEL_ID, product["image"], caption=generate_caption(product))
        print(f"Опубликован товар: {product['title']}")
    except Exception as e:
        print(f"Ошибка при публикации товара: {e}")

@bot.message_handler(commands=["next", "pause", "resume", "status", "log"])
def handle_commands(message):
    global paused
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "У вас нет доступа")
        return

    cmd = message.text.strip().lower()
    if cmd == "/next":
        publish_product()
        bot.reply_to(message, "Товар опубликован")
    elif cmd == "/pause":
        paused = True
        bot.reply_to(message, "Пауза активирована")
    elif cmd == "/resume":
        paused = False
        bot.reply_to(message, "Пауза отключена")
    elif cmd == "/status":
        status = "на паузе" if paused else "активен"
        bot.reply_to(message, f"Статус: {status}")
    elif cmd == "/log":
        bot.reply_to(message, f"Использовано товаров: {len(used_products)}")

def scheduler_loop():
    schedule.every().day.at(f"{POST_HOUR:02d}:00").do(publish_product)
    while True:
        schedule.run_pending()
        time.sleep(60)

import threading
threading.Thread(target=scheduler_loop).start()

print("Бот запущен. Ожидаем публикации...")
bot.infinity_polling()
