import os
from groq import Groq
from datetime import datetime


def get_client() -> Groq:
    return Groq(api_key=os.getenv("GROQ_API_KEY", ""))


def build_prompt(articles: list[dict]) -> str:
    articles_text = ""
    for i, article in enumerate(articles, 1):
        articles_text += f"""
--- Статья {i} ---
Источник: {article.get('source', 'Unknown')}
Заголовок: {article.get('title', '')}
Текст: {article.get('text', '')[:1500]}
"""

    return f"""Ты — опытный финансовый аналитик, специализирующийся на криптовалютах и акциях.

Проанализируй следующие новости и дай конкретные торговые рекомендации.

{articles_text}

На основе этих новостей дай ответ СТРОГО в следующем формате:

АНАЛИЗ РЫНКА ({datetime.now().strftime('%d.%m.%Y %H:%M')})

ПОКУПКА (РОСТ)
Перечисли 2-4 актива с потенциалом роста:
- Актив: [название/тикер]
- Причина: [краткое объяснение]
- Потенциал: [%]
- Риск: [низкий/средний/высокий]

ПРОДАЖА/ШОРТ (ПАДЕНИЕ)
Перечисли 2-4 актива с потенциалом падения:
- Актив: [название/тикер]
- Причина: [краткое объяснение]
- Потенциал: [%]
- Риск: [низкий/средний/высокий]

ВАЖНЫЕ СОБЫТИЯ
[2-3 ключевых события влияющих на рынок]

ОБЩИЙ НАСТРОЙ РЫНКА
[1-2 предложения о текущем состоянии рынка]

ДИСКЛЕЙМЕР: Это не финансовый совет. Торгуйте на свой страх и риск."""


async def analyze_news(articles: list[dict]) -> dict:
    if not articles:
        return {
            "success": False,
            "message": "Нет статей для анализа",
            "analysis": None,
            "raw_articles": []
        }

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your_groq_api_key_here":
        return {
            "success": False,
            "message": "GROQ_API_KEY не настроен в .env файле",
            "analysis": None,
            "raw_articles": articles
        }

    try:
        client = get_client()
        prompt = build_prompt(articles)

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7,
        )

        analysis_text = response.choices[0].message.content

        return {
            "success": True,
            "analysis": analysis_text,
            "articles_count": len(articles),
            "sources": list({a.get("source") for a in articles}),
            "timestamp": datetime.now().isoformat(),
            "raw_articles": articles
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Ошибка анализа: {str(e)}",
            "analysis": None,
            "raw_articles": articles
        }
