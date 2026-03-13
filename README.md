# 📊 Крипто/Акции Новостной Бот

Telegram бот для анализа финансовых новостей с ИИ рекомендациями.

## Установка

```bash
pip install -r requirements.txt
```

## Настройка (.env файл)

Открой `.env` и заполни:

```
TELEGRAM_BOT_TOKEN=твой_токен_бота
ANTHROPIC_API_KEY=твой_ключ_anthropic
NOTION_TOKEN=твой_notion_токен (опционально)
NOTION_PAGE_ID=id_страницы_notion (опционально)
```

### Где получить ключи:

1. **ANTHROPIC_API_KEY** → https://console.anthropic.com/
2. **NOTION_TOKEN** → https://www.notion.so/my-integrations (создай интеграцию)
3. **NOTION_PAGE_ID** → открой страницу в Notion, скопируй ID из URL

## Запуск

```bash
python main.py
```

## Команды бота

- `/start` — главное меню
- `/analyze` — запустить анализ сейчас
- `/help` — помощь

## Источники новостей

- Fortune
- CoinGecko (highlights + gainers)
- CoinDesk
- CoinMarketCap
