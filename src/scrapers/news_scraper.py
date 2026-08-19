"""AI news scraper — extracts 48-hour fresh articles from multiple AI news sources using RSS feeds."""
import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional
from src.scrapers.base import BaseScraper
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)

# RSS feeds are structured XML, much more reliable than scraping HTML
NEWS_SOURCES = [
    {
        "name": "TechCrunch AI",
        "rss_url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "base_url": "https://techcrunch.com",
        "content_selectors": ["article .entry-content", "article .article-content", ".post-content", "article"],
    },
    {
        "name": "VentureBeat AI",
        "rss_url": "https://venturebeat.com/ai/feed/",
        "base_url": "https://venturebeat.com",
        "content_selectors": ["article .article-content", ".post-body", "article"],
    },
    {
        "name": "The Verge AI",
        "rss_url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "base_url": "https://www.theverge.com",
        "content_selectors": ["article .article-body", ".article-content", "article"],
    },
    {
        "name": "Ars Technica AI",
        "rss_url": "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "base_url": "https://arstechnica.com",
        "content_selectors": ["article .article-content", ".post-content", "article"],
    },
    {
        "name": "MIT Tech Review AI",
        "rss_url": "https://www.technologyreview.com/feed/",
        "base_url": "https://www.technologyreview.com",
        "content_selectors": ["article .article-content", ".entry-content", "article"],
    },
    {
        "name": "Wired AI",
        "rss_url": "https://www.wired.com/feed/tag/ai/latest/rss",
        "base_url": "https://www.wired.com",
        "content_selectors": ["article .article-content", ".body-content", "article"],
    },
    {
        "name": "Google AI Blog",
        "rss_url": "https://blog.google/technology/ai/rss/",
        "base_url": "https://blog.google",
        "content_selectors": ["article .article-content", ".entry-content", "article"],
    },
    {
        "name": "OpenAI Blog",
        "rss_url": "https://openai.com/blog/rss.xml",
        "base_url": "https://openai.com",
        "content_selectors": ["article .article-content", ".entry-content", "article"],
    },
    {
        "name": "NVIDIA AI Blog",
        "rss_url": "https://blogs.nvidia.com/feed/",
        "base_url": "https://blogs.nvidia.com",
        "content_selectors": ["article .article-content", ".entry-content", "article"],
    },
    {
        "name": "Hugging Face Blog",
        "rss_url": "https://huggingface.co/blog/feed.xml",
        "base_url": "https://huggingface.co/blog",
        "content_selectors": ["article .article-content", ".entry-content", "article"],
    },
    {
        "name": "DeepMind Blog",
        "rss_url": "https://deepmind.google/blog/rss.xml",
        "base_url": "https://deepmind.google/blog",
        "content_selectors": ["article .article-content", ".entry-content", "article"],
    },
    {
        "name": "Towards Data Science",
        "rss_url": "https://towardsdatascience.com/feed",
        "base_url": "https://towardsdatascience.com",
        "content_selectors": ["article .article-content", ".entry-content", "article"],
    },
    {
        "name": "AI News",
        "rss_url": "https://www.artificialintelligence-news.com/feed/",
        "base_url": "https://www.artificialintelligence-news.com",
        "content_selectors": ["article .article-content", ".entry-content", "article"],
    },
    {
        "name": "VentureBeat AI",
        "rss_url": "https://venturebeat.com/category/ai/feed/",
        "base_url": "https://venturebeat.com",
        "content_selectors": ["article .article-content", ".post-body", "article"],
    },
]

# Namespaces for Atom feeds (used by The Verge etc.)
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class NewsScraper(BaseScraper):
    """Scrapes AI news articles from multiple sources via RSS feeds, filtering to last 48 hours."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.freshness_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    async def scrape(self, target_count: int = 100) -> list[dict]:
        records = []
        tasks = [self._scrape_source(src) for src in NEWS_SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                records.extend(result)
            elif isinstance(result, Exception):
                self.logger.error(f"News scraper error: {result}")

        # Sort by date, newest first
        records.sort(key=lambda x: x.get("content", {}).get("date") or "", reverse=True)

        self.logger.info(f"News Scraper: {len(records)} fresh articles collected")
        return records

    async def _scrape_source(self, source: dict) -> list[dict]:
        """Scrape a single news source via RSS feed."""
        records = []
        rss_url = source["rss_url"]

        # Fetch RSS/Atom feed as raw XML text
        xml_text = await self.http.get(rss_url)
        if not xml_text:
            self.logger.warning(f"Failed to fetch RSS feed: {rss_url}")
            return records

        # Parse the feed
        feed_items = self._parse_feed(xml_text)
        self.logger.info(f"{source['name']}: found {len(feed_items)} items in feed")

        # Filter for AI-related content and freshness
        fresh_items = []
        for item in feed_items:
            title = item.get("title", "")
            description = item.get("description", "")
            link = item.get("link", "")

            # Check if AI-related
            combined = f"{title} {description}".lower()
            ai_keywords = ["ai", "artificial intelligence", "machine learning", "ml",
                          "deep learning", "neural", "gpt", "llm", "chatgpt",
                          "openai", "anthropic", "google ai", "meta ai",
                          "transformer", "generative", "diffusion", "copilot",
                          "gemini", "claude", "deepseek", "mistral"]
            # TechCrunch AI category feed is already filtered, but check others
            is_ai_category = "artificial-intelligence" in rss_url or "/ai/" in rss_url
            if not is_ai_category and not any(kw in combined for kw in ai_keywords):
                continue

            # Check freshness
            pub_date = item.get("pub_date")
            if pub_date:
                if isinstance(pub_date, str):
                    try:
                        pub_date = dateparser.parse(pub_date)
                    except Exception:
                        pub_date = None

                if pub_date and hasattr(pub_date, 'tzinfo') and pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)

                if pub_date and pub_date < self.freshness_cutoff:
                    continue  # Skip articles older than 24h

            fresh_items.append(item)

        self.logger.info(f"{source['name']}: {len(fresh_items)} fresh AI articles")

        # Fetch full article text for each fresh item (up to 20 per source)
        for item in fresh_items[:20]:
            record = await self._build_record(source, item)
            if record:
                records.append(record)

        return records

    def _parse_feed(self, xml_text: str) -> list[dict]:
        """Parse RSS 2.0 or Atom feed into a list of items."""
        items = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            self.logger.warning(f"Feed XML parse error: {e}")
            return items

        # Detect feed type
        tag = root.tag.lower()

        if "rss" in tag:
            # RSS 2.0 format
            for item_el in root.iter("item"):
                item = {
                    "title": self._get_text(item_el, "title"),
                    "link": self._get_text(item_el, "link"),
                    "description": self._get_text(item_el, "description"),
                    "pub_date": self._get_text(item_el, "pubDate") or self._get_text(item_el, "dc:date"),
                    "author": self._get_text(item_el, "author") or self._get_text(item_el, "dc:creator"),
                }
                if item["title"] and item["link"]:
                    items.append(item)

        elif "feed" in tag:
            # Atom format
            ns = ATOM_NS
            for entry in root.findall("atom:entry", ns):
                title_el = entry.find("atom:title", ns)
                title = title_el.text.strip() if title_el is not None and title_el.text else ""

                # Get link (prefer "alternate" rel)
                link = ""
                for link_el in entry.findall("atom:link", ns):
                    rel = link_el.get("rel", "alternate")
                    if rel == "alternate":
                        link = link_el.get("href", "")
                        break
                if not link:
                    link_el = entry.find("atom:link", ns)
                    if link_el is not None:
                        link = link_el.get("href", "")

                # Get summary/content
                desc_el = entry.find("atom:summary", ns)
                if desc_el is None:
                    desc_el = entry.find("atom:content", ns)
                description = ""
                if desc_el is not None and desc_el.text:
                    description = re.sub(r'<[^>]+>', '', desc_el.text).strip()

                # Get date
                pub_date = ""
                for date_tag in ["atom:published", "atom:updated", "atom:created"]:
                    date_el = entry.find(date_tag, ns)
                    if date_el is not None and date_el.text:
                        pub_date = date_el.text.strip()
                        break

                # Get author
                author = ""
                author_el = entry.find("atom:author/atom:name", ns)
                if author_el is not None and author_el.text:
                    author = author_el.text.strip()

                if title and link:
                    items.append({
                        "title": title,
                        "link": link,
                        "description": description,
                        "pub_date": pub_date,
                        "author": author,
                    })

        return items

    def _get_text(self, element, tag: str) -> str:
        """Get text content of a sub-element."""
        el = element.find(tag)
        if el is not None and el.text:
            return el.text.strip()
        return ""

    async def _build_record(self, source: dict, item: dict) -> Optional[dict]:
        """Build a news record from a feed item, optionally fetching full text."""
        title = item.get("title", "")
        link = item.get("link", "")

        if not title or not link:
            return None

        # Parse date
        pub_date = None
        date_str = item.get("pub_date", "")
        if date_str:
            try:
                pub_date = dateparser.parse(date_str)
                if pub_date and pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
            except Exception:
                pass

        # Try to get full article text
        full_text = item.get("description", "")
        full_text = re.sub(r'<[^>]+>', '', full_text).strip()  # strip HTML

        # If description is short, try fetching the article page
        if len(full_text) < 200:
            try:
                article_text = await self._fetch_article_text(link, source)
                if article_text and len(article_text) > len(full_text):
                    full_text = article_text
            except Exception:
                pass  # Use what we have from the feed

        if not full_text or len(full_text) < 30:
            full_text = title  # At minimum, use the title

        # Truncate for storage
        if len(full_text) > 5000:
            full_text = full_text[:5000] + "..."

        # Create summary
        summary = full_text[:500] + "..." if len(full_text) > 500 else full_text

        return {
            "schemaVersion": "1.0",
            "recordType": "NEWS",
            "source": {"name": source["name"], "url": link},
            "content": {
                "title": title,
                "author": item.get("author"),
                "date": pub_date.isoformat() if pub_date else datetime.now(timezone.utc).isoformat(),
                "full_text": full_text,
                "summary": summary,
                "category": "AI",
            },
            "collectedAt": datetime.utcnow().isoformat() + "Z",
        }

    async def _fetch_article_text(self, url: str, source: dict) -> Optional[str]:
        """Fetch full article text from the article page."""
        soup = await self.fetch_and_parse(url)
        if not soup:
            return None

        for selector in source.get("content_selectors", ["article"]):
            content_el = soup.select_one(selector)
            if content_el:
                # Remove scripts, styles, nav, footer, sidebar
                for tag in content_el.select("script, style, nav, footer, .sidebar, .ad, .advertisement"):
                    tag.decompose()
                text = self.clean_text(content_el.get_text(separator=" ", strip=True))
                if text and len(text) > 100:
                    return text

        # Fallback: get all paragraph text
        paragraphs = soup.select("p")
        text = " ".join(self.clean_text(p.get_text()) for p in paragraphs if p.get_text(strip=True))
        return text if len(text) > 50 else None
