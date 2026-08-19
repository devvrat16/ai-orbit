"""Base scraper class with common patterns for all scrapers."""
import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional
from bs4 import BeautifulSoup
from src.http_client import HttpClient
from src.storage import Storage

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for all scrapers."""
    def __init__(self, http_client: HttpClient, storage: Storage):
        self.http = http_client
        self.storage = storage
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def scrape(self, target_count: int) -> list[dict]:
        """Main scraping method. Returns list of raw records."""
        pass

    async def fetch_and_parse(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch URL and return parsed BeautifulSoup, or None on failure."""
        html = await self.http.get(url)
        if html:
            return BeautifulSoup(html, "lxml")
        return None

    async def fetch_json(self, url: str, headers: Optional[dict] = None) -> Optional[dict]:
        """Fetch JSON endpoint."""
        return await self.http.get_json(url, extra_headers=headers)

    def parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML string into BeautifulSoup."""
        return BeautifulSoup(html, "lxml")

    def extract_text(self, element, strip: bool = True) -> Optional[str]:
        """Safely extract text from a BeautifulSoup element."""
        if element is None:
            return None
        text = element.get_text(strip=strip)
        return text if text else None

    def extract_attribute(self, element, attr: str) -> Optional[str]:
        """Safely extract an attribute from an element."""
        if element is None:
            return None
        val = element.get(attr)
        return val.strip() if isinstance(val, str) else None

    async def run(self, target_count: int = 500) -> list[dict]:
        """Run scraper with logging and deduplication."""
        name = self.__class__.__name__
        logger.info(f"Starting {name} (target: {target_count})")
        start = datetime.utcnow()

        records = await self.scrape(target_count)

        elapsed = (datetime.utcnow() - start).total_seconds()
        logger.info(f"{name}: collected {len(records)} records in {elapsed:.1f}s")
        return records

    @staticmethod
    def clean_text(text: str) -> str:
        """Clean extracted text: collapse whitespace, strip."""
        if not text:
            return ""
        import re
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def parse_int(text: str) -> Optional[int]:
        """Parse integer from text, handling commas and suffixes like '1.5k'."""
        if not text:
            return None
        import re
        text = text.lower().replace(",", "").strip()
        match = re.search(r'(\d+(?:\.\d+)?)\s*([kmb])?', text)
        if match:
            num = float(match.group(1))
            suffix = match.group(2) or ""
            multipliers = {"k": 1000, "m": 1_000_000, "b": 1_000_000_000}
            return int(num * multipliers.get(suffix, 1))
        try:
            return int(text)
        except (ValueError, TypeError):
            return None
