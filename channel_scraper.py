"""
Парсер публичных Telegram-каналов через t.me/s/
Не требует API_ID / API_HASH — работает через веб-интерфейс Telegram.
"""

import re
import logging
import httpx
from bs4 import BeautifulSoup, NavigableString

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# HTML-теги, которые поддерживает Telegram Bot API
ALLOWED_TAGS = {
    'b', 'strong', 'i', 'em', 'u', 's', 'strike', 'del',
    'a', 'code', 'pre', 'tg-emoji',
}


def extract_html(element) -> str:
    """Извлечь текст с допустимыми HTML-тегами из BeautifulSoup-элемента."""
    if element is None:
        return ''

    result = []
    for child in element.children:
        if isinstance(child, NavigableString):
            result.append(str(child))
        elif hasattr(child, 'name') and child.name:
            tag = child.name.lower()
            if tag == 'a':
                href = child.get('href', '')
                inner = extract_html(child)
                if href and inner:
                    result.append(f'<a href="{href}">{inner}</a>')
                else:
                    result.append(inner)
            elif tag in ALLOWED_TAGS:
                inner = extract_html(child)
                result.append(f'<{tag}>{inner}</{tag}>')
            elif tag == 'br':
                result.append('\n')
            else:
                # Для неподдерживаемых тегов — только внутренний текст
                result.append(extract_html(child))

    return ''.join(result)


async def get_channel_posts(channel_username: str, limit: int = 5) -> list[dict]:
    """
    Получить последние посты из публичного Telegram-канала.
    Возвращает список постов с текстом, фото, ID.
    """
    username = channel_username.lstrip('@').strip()
    url = f'https://t.me/s/{username}'

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            resp = await client.get(url, headers=HEADERS)
            if resp.status_code != 200:
                logger.warning(f'@{username}: HTTP {resp.status_code}')
                return []
    except Exception as e:
        logger.error(f'Ошибка получения @{username}: {e}')
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    posts = []

    # Находим все блоки сообщений
    message_wraps = soup.find_all('div', class_='tgme_widget_message_wrap')

    for wrap in message_wraps[-limit:]:
        msg_div = wrap.find('div', class_='tgme_widget_message')
        if not msg_div:
            continue

        # Получаем ID сообщения из data-post="channelname/123"
        data_post = msg_div.get('data-post', '')
        if not data_post:
            continue
        try:
            msg_id = int(data_post.split('/')[-1])
        except (ValueError, IndexError):
            continue

        # Пропускаем сервисные сообщения
        if 'tgme_widget_message_service' in msg_div.get('class', []):
            continue

        # Извлекаем текст с форматированием
        text_div = msg_div.find('div', class_='tgme_widget_message_text')
        text_html = ''
        text_plain = ''
        if text_div:
            text_html = extract_html(text_div).strip()
            text_plain = text_div.get_text(separator='\n', strip=True)

        # Ищем фото (background-image в стиле)
        photo_url = None
        photo_wrap = msg_div.find(
            lambda tag: tag.name and
            any('photo_wrap' in c for c in tag.get('class', []))
        )
        if photo_wrap:
            style = photo_wrap.get('style', '')
            match = re.search(r"url\(['\"]?([^'\")\s]+)['\"]?\)", style)
            if match:
                photo_url = match.group(1)

        # Ищем видео
        video_url = None
        video_elem = msg_div.find('video')
        if video_elem:
            video_url = video_elem.get('src') or video_elem.get('data-src')

        # Ссылка на оригинальный пост
        post_link = f'https://t.me/{username}/{msg_id}'

        posts.append({
            'id': msg_id,
            'channel': username,
            'text_html': text_html,
            'text_plain': text_plain,
            'photo_url': photo_url,
            'video_url': video_url,
            'post_link': post_link,
        })

    return posts
