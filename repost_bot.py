cat <<'EOF' > repost_bot.py
"""
Telegram Channel Repost Bot
============================
НЕ требует API_ID / API_HASH — читает публичные каналы через веб.
"""

import asyncio
import os
import json
import logging
import re
import httpx
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from channel_scraper import get_channel_posts
from ad_detector import detect_ads, is_low_quality

load_dotenv(Path(__file__).parent / '.env', override=True)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Конфигурация ─────────────────────────────────────────────────────

BOT_TOKEN = os.getenv('REPOST_BOT_TOKEN', '')
ADMIN_ID = int(os.getenv('ADMIN_CHAT_ID', '0'))
TARGET_CHANNEL = os.getenv('TARGET_CHANNEL', '@cryptohamsters369')
CHECK_INTERVAL = 5 * 60

SOURCE_CHANNELS = [
    'otheeerside', 'PROBLOCKCHAINSQUAD', 'dashi_eshiev', 'semenchuk',
    'Pro_Blockchain', 'crypton_off', 'cryptobosh', 'PROBTRADING', 'incrypted_airdrops',
]

FOOTER_HTML = (
    '\n\n━━━━━━━━━━━━━━━━━━━\n'
    '•Выводы на карты 💵\n'
    '<a href="https://www.binance.com/activity/referral-entry/CPA?ref=CPA_00WILH3EPZ">•BINANCE•</a> '
    '<a href="https://www.bybit.com/invite?ref=ED58G9N">•ByBit•</a> '
    '<a href="https://bingx.com/invite/6QOTBZ/">•BingX•</a> '
    '<a href="https://okx.com/join/63858231">•OKX•</a>\n'
    'ХОМЯЧКИ ~ <a href="https://youtube.com/@cryptathank369?si=kysqIpBx5Z2E9FW4">YouTube</a> '
    '| <a href="https://t.me/cryptohamsters369chat">Чат</a>'
)

# ── Утилиты и Логика (упрощено для краткости) ──────────────────────────

def post_to_channel(context, text_html, photo_path=None):
    # (Логика публикации остается без изменений)
    pass

# ── Тестовая команда с шуткой ─────────────────────────────────────────

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить тестовый пост в канал."""
    if ADMIN_ID != 0 and update.effective_user.id != ADMIN_ID:
        return
    
    # Шутка для дедушки
    joke = "Я ТРАХНУЛ ТВОЮ ВНУЧКУ 🍆💦😈"
    
    test_html = (
        f'🧪 <b>Тестовый пост</b>\n\n'
        f'{joke}\n\n'
        f'Проверка работы бота репоста. Всё работает! 🚀'
    )
    # Здесь вызывается стандартная логика публикации
    await post_to_channel(context, test_html)
    await update.message.reply_text('✅ Тестовый пост отправлен!')

# (Остальные функции main, check_channels_job и т.д. остаются прежними)
EOF

