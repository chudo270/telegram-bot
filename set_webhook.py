import asyncio
from aiogram import Bot
import os
from dotenv import load_dotenv

async def set_webhook():
    bot_token = os.getenv("BOT_TOKEN")
    webhook_url = os.getenv("WEBHOOK_URL")
    
    if not bot_token or not webhook_url:
        print("Ошибка: отсутствует BOT_TOKEN или WEBHOOK_URL")
        return
    
    bot = Bot(token=bot_token)
    await bot.set_webhook(webhook_url)
    print(f"Webhook установлен: {webhook_url}")

if __name__ == "__main__":
    asyncio.run(set_webhook())
