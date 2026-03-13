import os
import httpx
from datetime import datetime


NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def get_headers() -> dict:
    token = os.getenv("NOTION_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


async def find_or_create_database(page_id: str) -> str | None:
    """Find existing 'Новости и Аналитика' database or create it."""
    async with httpx.AsyncClient() as client:
        # Search for existing database
        response = await client.post(
            f"{NOTION_API_URL}/search",
            headers=get_headers(),
            json={"query": "Новости и Аналитика", "filter": {"value": "database", "property": "object"}},
            timeout=15,
        )

        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                return results[0]["id"]

        # Create new database
        db_data = {
            "parent": {"type": "page_id", "page_id": page_id},
            "title": [{"type": "text", "text": {"content": "📊 Новости и Аналитика"}}],
            "properties": {
                "Название": {"title": {}},
                "Дата": {"date": {}},
                "Тип": {
                    "select": {
                        "options": [
                            {"name": "Анализ", "color": "blue"},
                            {"name": "Новость", "color": "green"},
                            {"name": "Рекомендация", "color": "red"},
                        ]
                    }
                },
                "Источники": {"rich_text": {}},
                "Статей": {"number": {}},
            },
        }

        response = await client.post(
            f"{NOTION_API_URL}/databases",
            headers=get_headers(),
            json=db_data,
            timeout=15,
        )

        if response.status_code == 200:
            return response.json()["id"]

    return None


def text_block(content: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": content[:2000]}}]
        },
    }


def heading_block(content: str, level: int = 2) -> dict:
    h_type = f"heading_{level}"
    return {
        "object": "block",
        "type": h_type,
        h_type: {
            "rich_text": [{"type": "text", "text": {"content": content}}]
        },
    }


def divider_block() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


async def save_analysis_to_notion(result: dict) -> bool:
    """Save analysis result to Notion database."""
    token = os.getenv("NOTION_TOKEN", "")
    page_id = os.getenv("NOTION_PAGE_ID", "")

    if not token or token == "your_notion_integration_token_here":
        print("Notion token not configured, skipping save")
        return False

    if not page_id or page_id == "your_notion_page_id_here":
        print("Notion page ID not configured, skipping save")
        return False

    db_id = await find_or_create_database(page_id)
    if not db_id:
        print("Could not find or create Notion database")
        return False

    now = datetime.now()
    analysis_text = result.get("analysis", "")
    sources = ", ".join(result.get("sources", []))
    articles_count = result.get("articles_count", 0)

    # Split analysis into chunks for Notion blocks (2000 char limit per block)
    blocks = []
    blocks.append(heading_block("📊 Анализ рынка", 2))

    if analysis_text:
        chunk_size = 1900
        for i in range(0, len(analysis_text), chunk_size):
            chunk = analysis_text[i:i + chunk_size]
            blocks.append(text_block(chunk))

    blocks.append(divider_block())
    blocks.append(heading_block("📰 Источники", 3))
    blocks.append(text_block(f"Источники: {sources}"))
    blocks.append(text_block(f"Обработано статей: {articles_count}"))

    # Add article links
    if result.get("raw_articles"):
        blocks.append(heading_block("🔗 Статьи", 3))
        for article in result["raw_articles"][:10]:
            title = article.get("title", "")[:100]
            url = article.get("url", "")
            src = article.get("source", "")
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"[{src}] {title} "}},
                        {"type": "text", "text": {"content": url, "link": {"url": url}} if url else {"content": ""}}
                    ]
                }
            })

    page_data = {
        "parent": {"database_id": db_id},
        "properties": {
            "Название": {
                "title": [{"type": "text", "text": {"content": f"Анализ {now.strftime('%d.%m.%Y %H:%M')}"}}]
            },
            "Дата": {"date": {"start": now.isoformat()}},
            "Тип": {"select": {"name": "Анализ"}},
            "Источники": {"rich_text": [{"type": "text", "text": {"content": sources[:2000]}}]},
            "Статей": {"number": articles_count},
        },
        "children": blocks[:100],  # Notion limit
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{NOTION_API_URL}/pages",
            headers=get_headers(),
            json=page_data,
            timeout=30,
        )

        if response.status_code in (200, 201):
            page_url = response.json().get("url", "")
            print(f"Saved to Notion: {page_url}")
            return True
        else:
            print(f"Notion save failed: {response.status_code} - {response.text[:300]}")
            return False
