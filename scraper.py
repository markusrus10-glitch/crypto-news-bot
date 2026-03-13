import httpx
from bs4 import BeautifulSoup
import asyncio

NEWS_SOURCES = [
    # === КРИПТО ===
    {
        "name": "CoinDesk Markets",
        "url": "https://www.coindesk.com/markets/",
        "selectors": {"articles": "article", "title": "h4,h3,h2", "link": "a"}
    },
    {
        "name": "CoinMarketCap News",
        "url": "https://coinmarketcap.com/headlines/news/",
        "selectors": {"articles": "div", "title": "h3,h2,p", "link": "a"}
    },
    {
        "name": "CoinGecko Highlights",
        "url": "https://www.coingecko.com/en/highlights",
        "selectors": {"articles": "article", "title": "h3,h2,h1", "link": "a"}
    },
    {
        "name": "CoinGecko Gainers",
        "url": "https://www.coingecko.com/research/publications/top-crypto-gainers",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    {
        "name": "CryptoPanic",
        "url": "https://cryptopanic.com/news/",
        "selectors": {"articles": "article", "title": "h2,h3,a", "link": "a"}
    },
    {
        "name": "Decrypt",
        "url": "https://decrypt.co/news",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    {
        "name": "The Block",
        "url": "https://www.theblock.co/latest",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    {
        "name": "Cointelegraph",
        "url": "https://cointelegraph.com/",
        "selectors": {"articles": "article", "title": "h2,h3", "link": "a"}
    },
    {
        "name": "Bitcoin Magazine",
        "url": "https://bitcoinmagazine.com/articles",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    {
        "name": "Coinbase Blog",
        "url": "https://www.coinbase.com/blog",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    # === АКЦИИ И ФИНАНСЫ ===
    {
        "name": "Fortune Finance",
        "url": "https://fortune.com/section/finance/",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    {
        "name": "Reuters Finance",
        "url": "https://www.reuters.com/finance/",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    {
        "name": "MarketWatch",
        "url": "https://www.marketwatch.com/latest-news",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    {
        "name": "Investing.com Crypto",
        "url": "https://www.investing.com/news/cryptocurrency-news",
        "selectors": {"articles": "article", "title": "h3,h2,a", "link": "a"}
    },
    {
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/topic/crypto/",
        "selectors": {"articles": "article,li", "title": "h3,h2", "link": "a"}
    },
    {
        "name": "Seeking Alpha Crypto",
        "url": "https://seekingalpha.com/market-news/crypto",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    {
        "name": "Barron's Markets",
        "url": "https://www.barrons.com/topics/markets",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    # === АНАЛИТИКА И ИССЛЕДОВАНИЯ ===
    {
        "name": "Multicoin Capital",
        "url": "https://multicoin.capital/writing/",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    {
        "name": "Messari",
        "url": "https://messari.io/news",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
    {
        "name": "Glassnode Insights",
        "url": "https://insights.glassnode.com/",
        "selectors": {"articles": "article", "title": "h3,h2", "link": "a"}
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_page(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await client.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None


def extract_articles(html: str, source: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Try to get article links and titles
    links = soup.find_all("a", href=True)
    seen = set()

    for link in links:
        href = link.get("href", "")
        title = link.get_text(strip=True)

        # Filter short titles and duplicates
        if len(title) < 20:
            continue
        if href in seen:
            continue
        seen.add(href)

        # Make absolute URL
        if href.startswith("/"):
            base = "/".join(source["url"].split("/")[:3])
            href = base + href
        elif not href.startswith("http"):
            continue

        results.append({"title": title, "url": href, "source": source["name"]})

        if len(results) >= 10:
            break

    return results


async def fetch_article_text(client: httpx.AsyncClient, url: str) -> str:
    html = await fetch_page(client, url)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    # Remove scripts/styles
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    paragraphs = soup.find_all("p")
    text = " ".join(p.get_text(strip=True) for p in paragraphs[:20])
    return text[:3000]  # Limit to 3000 chars per article


async def scrape_all_sources() -> list[dict]:
    all_articles = []

    async with httpx.AsyncClient() as client:
        # Fetch main pages in parallel
        tasks = [fetch_page(client, src["url"]) for src in NEWS_SOURCES]
        pages = await asyncio.gather(*tasks)

        article_candidates = []
        for src, html in zip(NEWS_SOURCES, pages):
            if html:
                articles = extract_articles(html, src)
                article_candidates.extend(articles)

        print(f"Found {len(article_candidates)} article candidates")

        # Fetch full text for top articles (limit to 25 total)
        fetch_tasks = []
        for article in article_candidates[:25]:
            fetch_tasks.append(fetch_article_text(client, article["url"]))

        texts = await asyncio.gather(*fetch_tasks)

        for article, text in zip(article_candidates[:25], texts):
            if text:
                article["text"] = text
                all_articles.append(article)

    return all_articles
