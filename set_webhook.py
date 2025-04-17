import asyncio
from aiogram import Bot
import os

async def set_webhook():
    bot_token = os.getenv("BOT_TOKEN")
    webhook_url = "https://worker-production-c8d5.up.railway.app/webhook"
    
    if not bot_token:
        print("Ошибка: отсутствует BOT_TOKEN")
        return
    
    bot = Bot(token=bot_token)
    await bot.set_webhook(webhook_url)
    print(f"Webhook установлен: {webhook_url}")

if __name__ == "__main__":
    asyncio.run(set_webhook())
