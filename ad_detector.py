"""
Детектор рекламы и реферальных ссылок в постах Telegram-каналов.
"""

import re
from urllib.parse import urlparse, parse_qs

# Параметры в URL, указывающие на реферальную ссылку
REFERRAL_PARAMS = [
    'ref', 'refid', 'referral', 'affiliate', 'aff', 'partner',
    'utm_source', 'utm_medium', 'utm_campaign',
    'click_id', 'clickid', 'subid', 'invite',
]

# Паттерны в пути URL
REFERRAL_PATH_PATTERNS = [
    r'/invite/', r'/ref/', r'/referral/', r'/affiliate/',
    r'/partner/', r'/promo/', r'/signup\?', r'/register\?',
    r'/join/', r'/r/',
]

# Домены коротких ссылок (часто используются для маскировки реферальных)
SHORT_LINK_DOMAINS = [
    'bit.ly', 'tinyurl.com', 'goo.gl', 't.co', 'ow.ly',
    'is.gd', 'buff.ly', 'clck.ru', 'taplink.cc',
    'linktr.ee', 'lnk.to', 'cutt.ly', 'rb.gy',
]

# Ключевые слова рекламы (русский)
AD_KEYWORDS_RU = [
    'реклама', '#реклама', '#промо', '#партнер',
    'промокод', 'промо-код', 'промо код',
    'партнёрск', 'партнерск',
    'спонсор',
    'используй код', 'по промокоду',
    'переходи по ссылке', 'перейди по ссылке',
    'зарегистрируйся по', 'регистрация по ссылке',
    'скидка по', 'получи скидку', 'получи бонус',
    'бесплатный доступ по',
    'розыгрыш призов',
    'erid:',  # Обязательная маркировка рекламы в РФ
    'токен рекламы',
    'оплаченн',
    'заказчик рекламы',
]

# Ключевые слова рекламы (английский)
AD_KEYWORDS_EN = [
    '#ad', '#sponsored', '#partner', '#promo',
    'use code', 'promo code', 'discount code',
    'sign up now', 'register now',
    'limited offer', 'exclusive deal',
    'sponsored by', 'brought to you by',
    'paid partnership',
]


def extract_urls(text: str) -> list[str]:
    """Извлечь все URL из текста."""
    pattern = r'https?://[^\s<>\[\]()\"\'，。]+'
    return re.findall(pattern, text, re.IGNORECASE)


def is_referral_url(url: str) -> bool:
    """Проверить, является ли URL реферальным."""
    try:
        parsed = urlparse(url.lower())
        domain = parsed.netloc.replace('www.', '')

        # Короткие ссылки
        if domain in SHORT_LINK_DOMAINS:
            return True

        # Реферальные параметры в query string
        params = parse_qs(parsed.query)
        for param in params:
            if param.lower() in REFERRAL_PARAMS:
                return True

        # Реферальные паттерны в пути
        for pattern in REFERRAL_PATH_PATTERNS:
            if re.search(pattern, parsed.path, re.IGNORECASE):
                return True

    except Exception:
        pass

    return False


def detect_ads(text: str) -> dict:
    """
    Проанализировать текст на наличие рекламы и реферальных ссылок.

    Returns:
        {
            'is_suspicious': bool,
            'confidence': float (0-1),
            'reasons': list[str]
        }
    """
    if not text:
        return {'is_suspicious': False, 'confidence': 0.0, 'reasons': []}

    reasons = []
    score = 0.0
    text_lower = text.lower()

    # Проверка ключевых слов (русский)
    for keyword in AD_KEYWORDS_RU:
        if keyword.lower() in text_lower:
            reasons.append(f'Ключевое слово: "{keyword}"')
            score += 0.4

    # Проверка ключевых слов (английский)
    for keyword in AD_KEYWORDS_EN:
        if keyword.lower() in text_lower:
            reasons.append(f'Keyword: "{keyword}"')
            score += 0.3

    # Проверка URL
    urls = extract_urls(text)
    referral_urls = [u for u in urls if is_referral_url(u)]
    if referral_urls:
        for url in referral_urls[:3]:
            reasons.append(f'Реферальная ссылка: {url[:80]}...')
        score += 0.5 * len(referral_urls)

    # ERID маркировка (обязательная для рекламы в РФ)
    if re.search(r'erid[:\s]*[\w\d]+', text_lower):
        reasons.append('Маркировка рекламы (ERID)')
        score += 0.9

    # Слишком много ссылок в коротком посте
    if len(urls) > 5 and len(text) < 500:
        reasons.append(f'Много ссылок ({len(urls)}) в коротком посте')
        score += 0.3

    confidence = min(score, 1.0)

    return {
        'is_suspicious': confidence >= 0.3,
        'confidence': confidence,
        'reasons': reasons,
    }


# ── Фильтр качества контента ─────────────────────────────────────────

# Паттерны для определения "ценовых" постов (BTC 73000$ и т.п.)
PRICE_PATTERNS = [
    r'btc\s*[\d,.]+\s*[$€₽]',
    r'eth\s*[\d,.]+\s*[$€₽]',
    r'[A-Z]{2,6}\s*[\d,.]+\s*[$€₽k]',
    r'[\d,.]+\s*[$€₽]\s*[✅❌📈📉🟢🔴]',
]

# Слова, указывающие что пост — уведомление о закреплении
PINNED_PATTERNS = [
    r'pinned\s+[«"]',
    r'закрепил[аи]?\s+[«"]',
    r'закреплено\s+[«"]',
]

# Паттерны рекламных приглашений/CTA (без новостного контента)
PROMO_CTA_PATTERNS = [
    r'^вступ(ить|ай|айте)\s+в\b',
    r'^присоедин',
    r'^подпишись\b',
    r'^переход(и|ите)\s+по\b',
    r'^жми\s+(на\s+)?ссылку',
    r'^кликай\b',
    r'^регистрир',
    r'^записыва',
    r'^следи\s+за\b',
    r'^наш\s+канал\b',
    r'^наши\s+ссылки\b',
]

# Если пост содержит эти слова — скорее всего важный контент
QUALITY_KEYWORDS = [
    'airdrop', 'эйрдроп', 'дроп', 'листинг', 'listing',
    'новост', 'анонс', 'объявл', 'запуск', 'launch',
    'выход', 'обновлен', 'update', 'анализ', 'прогноз',
    'pump', 'dump', 'взлет', 'обвал', 'рост', 'падение',
    'хак', 'hack', 'взлом', 'партнерств', 'partnership',
    'mainnet', 'testnet', 'snapshot', 'snapshot',
    'токен', 'token', 'nft', 'defi', 'staking',
    'биржа', 'exchange', 'sec', 'регулятор', 'закон',
    'трамп', 'байден', 'etf', 'фонд',
    'инвест', 'invest', 'привлек', 'раунд', 'round',
    'важно', 'срочно', 'breaking', 'urgent',
    'whitelist', 'вайтлист', 'presale', 'пресейл',
]


def is_low_quality(text: str) -> tuple[bool, str]:
    """
    Проверить, является ли пост низкокачественным (не нужно публиковать).

    Returns: (is_low_quality: bool, reason: str)
    """
    if not text:
        return True, 'Пустой пост'

    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    # Слишком короткий пост (меньше 30 символов)
    if len(text_stripped) < 30:
        return True, f'Слишком короткий пост ({len(text_stripped)} символов)'

    # Уведомление о закреплении сообщения
    for pattern in PINNED_PATTERNS:
        if re.search(pattern, text_lower):
            return True, 'Уведомление о закреплении поста'

    # Рекламное приглашение / CTA без новостного контента
    for pattern in PROMO_CTA_PATTERNS:
        if re.search(pattern, text_lower):
            return True, 'Рекламное приглашение / CTA'

    # Только цены без контекста (короткий пост с ценами)
    if len(text_stripped) < 150:
        price_matches = sum(
            1 for p in PRICE_PATTERNS
            if re.search(p, text_lower)
        )
        if price_matches >= 1:
            # Считаем строки — если почти все строки это цены
            lines = [l.strip() for l in text_stripped.split('\n') if l.strip()]
            price_lines = sum(
                1 for line in lines
                if re.search(r'[A-Z]{2,6}.*[\d,.]+.*[$€₽]|[\d,.]+.*[$€₽].*[✅❌]', line)
            )
            if lines and price_lines / len(lines) >= 0.6:
                return True, 'Пост только с ценами без новостного контекста'

    return False, ''
