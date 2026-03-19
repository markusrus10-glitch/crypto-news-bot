"""
Telegram Channel Repost Bot
============================
НЕ требует API_ID / API_HASH — читает публичные каналы через веб.

Как работает:
  1. Каждые 5 минут проверяет каналы-источники на новые посты
  2. Если пост чистый — автоматически публикует в ваш канал с футером
  3. Если найдена реклама/реф. ссылки — отправляет вам на модерацию

Настройка:
  1. Заполните .env файл (REPOST_BOT_TOKEN, ADMIN_CHAT_ID, TARGET_CHANNEL)
  2. Добавьте бота как админа в @cryptohamsters369
  3. Запустите: python repost_bot.py
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
CHECK_INTERVAL = 5 * 60  # Проверка каждые 5 минут

# Каналы-источники
SOURCE_CHANNELS = [
    'otheeerside',
    'PROBLOCKCHAINSQUAD',
    'dashi_eshiev',
    'semenchuk',
    'Pro_Blockchain',
    'crypton_off',
    'cryptobosh',
    'PROBTRADING',
    'incrypted_airdrops',
    # Приватный канал @t.me/+FuZP6k2mlY4yNmZi нельзя читать без API
    # Добавьте его юзернейм сюда если у него есть публичный @username
]

# Футер для каждого поста
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

# ── Хранилище данных ──────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / 'data'
DATA_DIR.mkdir(exist_ok=True)
TEMP_DIR = DATA_DIR / 'temp'
TEMP_DIR.mkdir(exist_ok=True)

PROCESSED_FILE = DATA_DIR / 'processed_ids.json'
SEEDED_FILE = DATA_DIR / '.seeded'  # Флаг первого запуска

processed_ids: set[str] = set()
pending_posts: dict[str, dict] = {}  # post_key -> данные поста
auto_post_queue: list[dict] = []    # Очередь чистых постов для публикации (1 в час)


def load_processed():
    global processed_ids
    if PROCESSED_FILE.exists():
        try:
            data = json.loads(PROCESSED_FILE.read_text(encoding='utf-8'))
            processed_ids = set(data[-15000:])
        except Exception:
            processed_ids = set()


def save_processed():
    data = list(processed_ids)[-15000:]
    PROCESSED_FILE.write_text(json.dumps(data), encoding='utf-8')


def is_first_run() -> bool:
    return not SEEDED_FILE.exists()


def mark_seeded():
    SEEDED_FILE.write_text(datetime.now().isoformat(), encoding='utf-8')


def make_key(channel: str, msg_id: int) -> str:
    return f'{channel}:{msg_id}'


def is_processed(channel: str, msg_id: int) -> bool:
    return make_key(channel, msg_id) in processed_ids


def mark_processed(channel: str, msg_id: int):
    processed_ids.add(make_key(channel, msg_id))
    save_processed()


# ── Утилиты ───────────────────────────────────────────────────────────

def strip_links(html_text: str) -> str:
    """Убрать ссылки из HTML, оставить только текст ссылок."""
    cleaned = re.sub(r'<a\s+[^>]*>(.*?)</a>', r'\1', html_text)
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = re.sub(r'  +', ' ', cleaned)
    return cleaned.strip()


def safe_html(text: str, max_len: int = 4096) -> str:
    """Обрезать текст до допустимой длины."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + '...'


async def download_image(url: str, filename: str) -> str | None:
    """Скачать изображение по URL и сохранить во временную папку."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                path = TEMP_DIR / filename
                path.write_bytes(resp.content)
                return str(path)
    except Exception as e:
        logger.error(f'Ошибка скачивания изображения: {e}')
    return None


def cleanup_file(path: str | None):
    """Удалить временный файл."""
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


# ── Публикация ────────────────────────────────────────────────────────

async def post_to_channel(
    context: ContextTypes.DEFAULT_TYPE,
    text_html: str,
    photo_path: str | None = None,
) -> bool:
    """Опубликовать пост в целевой канал с футером."""
    full_text = text_html + FOOTER_HTML

    try:
        if photo_path and os.path.exists(photo_path):
            caption = safe_html(full_text, max_len=1024)
            with open(photo_path, 'rb') as f:
                await context.bot.send_photo(
                    chat_id=TARGET_CHANNEL,
                    photo=f,
                    caption=caption,
                    parse_mode='HTML',
                )
        else:
            text = safe_html(full_text, max_len=4096)
            await context.bot.send_message(
                chat_id=TARGET_CHANNEL,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True,
            )
        logger.info(f'✅ Пост опубликован в {TARGET_CHANNEL}')
        return True
    except Exception as e:
        logger.error(f'❌ Ошибка публикации: {e}')
        return False


async def send_for_moderation(
    context: ContextTypes.DEFAULT_TYPE,
    post: dict,
    ad_reasons: list,
):
    """Отправить подозрительный пост админу для проверки."""
    reasons_lines = '\n'.join(f'  • {r}' for r in ad_reasons)

    mod_text = (
        f'📢 <b>Пост из @{post["channel"]}</b>\n'
        f'⚠️ <b>Подозрение на рекламу:</b>\n{reasons_lines}\n'
        f'━━━━━━━━━━━━━━━━━━━\n'
        f'{safe_html(post["text_html"], 2500)}\n'
        f'━━━━━━━━━━━━━━━━━━━'
    )

    post_key = f'{post["channel"]}_{post["id"]}'
    pending_posts[post_key] = post

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton('✅ Опубликовать', callback_data=f'approve:{post_key}'),
            InlineKeyboardButton('❌ Отклонить', callback_data=f'reject:{post_key}'),
        ],
        [
            InlineKeyboardButton(
                '✏️ Опубликовать без чужих ссылок',
                callback_data=f'clean:{post_key}',
            ),
        ],
    ])

    try:
        photo_path = post.get('photo_path')
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                await context.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=f,
                    caption=safe_html(mod_text, 1024),
                    parse_mode='HTML',
                    reply_markup=keyboard,
                )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=safe_html(mod_text, 4096),
                parse_mode='HTML',
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        logger.info(f'📨 Отправлено на модерацию: @{post["channel"]} #{post["id"]}')
    except Exception as e:
        logger.error(f'❌ Ошибка отправки на модерацию: {e}')


# ── Джоб: проверка каналов ────────────────────────────────────────────

async def check_channels_job(context: ContextTypes.DEFAULT_TYPE):
    """Основной джоб — проверяет каналы на новые посты."""
    first_run = is_first_run()
    if first_run:
        logger.info('🔍 Первый запуск — сканирую каналы (без публикации старых постов)...')

    new_posts_count = 0

    for channel in SOURCE_CHANNELS:
        try:
            posts = await get_channel_posts(channel, limit=5)
        except Exception as e:
            logger.error(f'Ошибка проверки @{channel}: {e}')
            continue

        for post in posts:
            if is_processed(channel, post['id']):
                continue

            mark_processed(channel, post['id'])

            # При первом запуске просто помечаем как обработанные (не постим)
            if first_run:
                continue

            new_posts_count += 1

            # Скачиваем фото если есть
            if post.get('photo_url'):
                photo_path = await download_image(
                    post['photo_url'],
                    f"{channel}_{post['id']}.jpg",
                )
                post['photo_path'] = photo_path

            # Фильтр качества: пропускаем ценовые посты, pinned и т.п.
            low_q, lq_reason = is_low_quality(post['text_plain'])
            if low_q:
                logger.info(f'⏭ Пропускаю пост @{channel} #{post["id"]}: {lq_reason}')
                cleanup_file(post.get('photo_path'))
                continue

            # Проверяем на рекламу
            detection = detect_ads(post['text_plain'])

            if detection['is_suspicious']:
                # Отправляем на модерацию
                await send_for_moderation(context, post, detection['reasons'])
            else:
                # Добавляем в очередь (публикуется 1 раз в час)
                auto_post_queue.append(post)
                logger.info(f'📥 Пост @{channel} #{post["id"]} добавлен в очередь (позиция {len(auto_post_queue)})')

            # Небольшая задержка чтобы не заспамить
            await asyncio.sleep(3)

    if first_run:
        mark_seeded()
        logger.info('✅ Первичное сканирование завершено. Теперь буду постить только новые посты.')
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        '✅ <b>Первичное сканирование завершено!</b>\n\n'
                        f'Отсканировано {len(processed_ids)} существующих постов.\n'
                        'Теперь буду публиковать только <b>новые</b> посты.\n\n'
                        f'Слежу за {len(SOURCE_CHANNELS)} каналами.'
                    ),
                    parse_mode='HTML',
                )
            except Exception:
                pass
    elif new_posts_count:
        logger.info(f'📬 Обработано новых постов: {new_posts_count}')


# ── Джоб: публикация 1 поста в час ───────────────────────────────────

async def publish_queue_job(context: ContextTypes.DEFAULT_TYPE):
    """Публикует 1 пост из очереди каждый час."""
    if not auto_post_queue:
        logger.info('📭 Очередь пустая — нечего публиковать')
        return

    post = auto_post_queue.pop(0)
    logger.info(f'📤 Публикую из очереди: @{post["channel"]} #{post["id"]} (осталось в очереди: {len(auto_post_queue)})')

    # Убираем все чужие ссылки — только наш футер остаётся
    clean_text = strip_links(post['text_html'])

    # Если после удаления ссылок текст пустой или слишком короткий — пропускаем
    plain_after = re.sub(r'\s+', ' ', clean_text).strip()
    if len(plain_after) < 40:
        logger.info(f'⏭ Пропускаю пост @{post["channel"]} #{post["id"]}: после удаления ссылок текст слишком короткий ({len(plain_after)} символов)')
        cleanup_file(post.get('photo_path'))
        return

    success = await post_to_channel(context, clean_text, post.get('photo_path'))
    cleanup_file(post.get('photo_path'))

    if not success:
        logger.error('❌ Не удалось опубликовать пост из очереди')


# ── Команды бота ──────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_html(
        f'🤖 <b>Бот репоста каналов</b>\n\n'
        f'🆔 Ваш Telegram ID: <code>{uid}</code>\n'
        f'📢 Целевой канал: {TARGET_CHANNEL}\n'
        f'📰 Источников: {len(SOURCE_CHANNELS)}\n\n'
        f'Проверяю каналы каждые 5 минут.\n'
        f'Посты с рекламой → сюда на проверку.\n'
        f'Чистые посты → сразу в канал.\n\n'
        f'<b>Команды:</b>\n'
        f'/start — информация\n'
        f'/status — статистика\n'
        f'/check — проверить каналы сейчас\n'
        f'/channels — список каналов\n'
        f'/test — тестовый пост в канал\n\n'
        f'⚙️ Если ADMIN_CHAT_ID ещё не настроен, скопируй свой ID выше и впиши в .env'
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID != 0 and update.effective_user.id != ADMIN_ID:
        return
    seeded = '✅ Да' if not is_first_run() else '⏳ Нет (ожидает первой проверки)'
    await update.message.reply_html(
        f'📊 <b>Статус</b>\n\n'
        f'Просканировано постов: <b>{len(processed_ids)}</b>\n'
        f'Очередь к публикации: <b>{len(auto_post_queue)}</b> (1 пост/час)\n'
        f'На модерации: <b>{len(pending_posts)}</b>\n'
        f'Источников: <b>{len(SOURCE_CHANNELS)}</b>\n'
        f'Первичное сканирование: {seeded}'
    )


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запустить проверку каналов вручную."""
    if ADMIN_ID != 0 and update.effective_user.id != ADMIN_ID:
        return
    msg = await update.message.reply_text('⏳ Проверяю каналы...')
    await check_channels_job(context)
    await msg.edit_text('✅ Проверка завершена!')


async def cmd_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID != 0 and update.effective_user.id != ADMIN_ID:
        return
    ch_list = '\n'.join(f'  • @{ch}' for ch in SOURCE_CHANNELS)
    await update.message.reply_html(
        f'📰 <b>Каналы-источники ({len(SOURCE_CHANNELS)}):</b>\n\n'
        f'{ch_list}\n\n'
        f'🎯 Целевой канал: {TARGET_CHANNEL}'
    )


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить тестовый пост в канал."""
    if ADMIN_ID != 0 and update.effective_user.id != ADMIN_ID:
        return
    test_html = (
        '🧪 <b>Тестовый пост</b>\n\n'
        'Проверка работы бота репоста. Всё работает! 🚀'
    )
    success = await post_to_channel(context, test_html)
    if success:
        await update.message.reply_text('✅ Тестовый пост отправлен в канал!')
    else:
        await update.message.reply_text(
            '❌ Ошибка отправки.\n'
            'Проверь: бот добавлен как <b>админ</b> в канал?',
            parse_mode='HTML',
        )


# ── Обработчик кнопок модерации ───────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопки: Опубликовать / Без ссылок / Отклонить."""
    query = update.callback_query
    await query.answer()

    if ADMIN_ID != 0 and query.from_user.id != ADMIN_ID:
        await query.answer('⛔ Нет доступа', show_alert=True)
        return

    raw = query.data  # формат: "action:post_key"
    if ':' not in raw:
        return
    action, post_key = raw.split(':', 1)
    post = pending_posts.get(post_key)

    if not post:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text('⚠️ Пост не найден (уже обработан?)')
        return

    status_text = ''

    if action == 'approve':
        success = await post_to_channel(context, post['text_html'], post.get('photo_path'))
        status_text = '✅ Опубликовано!' if success else '❌ Ошибка публикации'

    elif action == 'clean':
        clean_html = strip_links(post['text_html'])
        success = await post_to_channel(context, clean_html, post.get('photo_path'))
        status_text = '✅ Опубликовано (без чужих ссылок)!' if success else '❌ Ошибка'

    elif action == 'reject':
        status_text = '❌ Отклонено'

    else:
        return

    # Очищаем
    cleanup_file(post.get('photo_path'))
    pending_posts.pop(post_key, None)

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        f'{status_text}\n📢 Источник: @{post["channel"]} #{post["id"]}'
    )


# ── Запуск ────────────────────────────────────────────────────────────

def print_bot_info():
    """Получить и вывести инфо о боте через прямой HTTP запрос."""
    import urllib.request
    import json as _json
    try:
        url = f'https://api.telegram.org/bot{BOT_TOKEN}/getMe'
        with urllib.request.urlopen(url, timeout=10) as r:
            data = _json.loads(r.read())
        if data.get('ok'):
            b = data['result']
            print('\n' + '='*55)
            print('  БОТ ЗАПУЩЕН!')
            print(f'  Имя     : {b.get("first_name", "")}')
            print(f'  Username: @{b.get("username", "")}')
            print(f'  ID      : {b.get("id", "")}')
            print('='*55)
            print(f'  Открой Telegram -> найди @{b.get("username","")}')
            print('  Напиши ему /start -> получишь свой ID')
            print('  Вставь ID в .env -> ADMIN_CHAT_ID=...')
            print('='*55 + '\n')
        else:
            print(f'Ошибка токена: {data}')
    except Exception as e:
        print(f'Не удалось получить инфо о боте: {e}')


def main():
    if not BOT_TOKEN or BOT_TOKEN == 'СЮДА_ТОКЕН_БОТА':
        print('Укажите REPOST_BOT_TOKEN в файле .env')
        return

    # Сразу выводим инфо о боте
    print_bot_info()

    if ADMIN_ID == 0:
        print('ADMIN_CHAT_ID = 0. Напиши боту /start чтобы узнать свой ID.')

    load_processed()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Регистрируем команды
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('status', cmd_status))
    app.add_handler(CommandHandler('check', cmd_check))
    app.add_handler(CommandHandler('channels', cmd_channels))
    app.add_handler(CommandHandler('test', cmd_test))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Джоб: проверка каналов каждые 5 минут
    app.job_queue.run_repeating(
        check_channels_job,
        interval=CHECK_INTERVAL,
        first=15,
    )

    # Джоб: публикация 1 поста в час
    app.job_queue.run_repeating(
        publish_queue_job,
        interval=60 * 60,  # каждые 60 минут
        first=60,          # первая публикация через 1 минуту после старта
    )

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == '__main__':
    main()
