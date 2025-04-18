# Telegram Bot for Product Publishing

Этот бот автоматически публикует товары в Telegram-канал по расписанию.  
Также поддерживает команды управления через личные сообщения Telegram.

## Основные функции:

- Автопубликация товаров ежедневно в 12:00 по МСК.
- Фильтрация: цена от 300₽, только товары с фото и описанием.
- Использует основной сайт и YML-файл в качестве резервного источника.
- Генерация описания, если отсутствует.
- Управление через команды: /next, /pause, /status, /log.
- Безопасный доступ только по Telegram ID владельца.

## Установка

1. Клонируй репозиторий:
   ```
   git clone https://github.com/chudo270/telegram-bot.git
   ```

2. Установи зависимости:
   ```
   pip install -r requirements.txt
   ```

3. Запусти бота:
   ```
   python main.py
   ```

## Авторизация

Для управления ботом через команды, используется Telegram ID владельца.

## Запуск на Render

- Укажи `worker` как тип сервиса.
- Убедись, что добавлены переменные окружения (если нужны токены, ключи и т.д.).
