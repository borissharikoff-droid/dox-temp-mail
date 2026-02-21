# TemperMail — Telegram Temp Mail Bot

Telegram-бот для временной почты на базе [Mail.tm](https://mail.tm) API.

## Функции

- Создание временной почты по кнопке
- Уведомления о новых письмах в Telegram
- Извлечение кодов и ссылок из писем
- Inline-кнопки для верификационных ссылок
- Предупреждение об устаревшей почте (1 час)

## Деплой на Railway

1. Создай проект на [Railway](https://railway.app)
2. Подключи репозиторий (Deploy from GitHub)
3. Добавь переменные окружения:
   - `TELEGRAM_BOT_TOKEN` — токен бота от @BotFather
   - `WEBHOOK_URL` — публичный URL приложения (например `https://your-app.railway.app`)
4. Railway автоматически задаёт `PORT`

После первого деплоя скопируй URL приложения и укажи его в `WEBHOOK_URL`, затем перезапусти.

## Локальный запуск

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=your_token
export WEBHOOK_URL=https://your-ngrok-url  # для webhook
python app.py
```

Для локальной разработки с webhook нужен ngrok или аналог.

## Структура

```
├── app.py           # Flask + webhook
├── config.py        # Конфигурация
├── db.py            # SQLite
├── bot/
│   ├── handlers.py  # Обработчики команд и кнопок
│   ├── mail_service.py   # Mail.tm API
│   ├── message_parser.py # Парсинг писем
│   ├── sender.py    # Отправка в Telegram из фона
│   └── sse_listener.py   # Polling новых писем
```
