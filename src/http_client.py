"""Async HTTP client with retry, backoff, jitter, and rate limiting."""
import asyncio
import random
import time
import logging
from typing import Optional
import aiohttp
from config import (
    SCRAPE_CONCURRENCY, SCRAPE_TIMEOUT, SCRAPE_MAX_RETRIES,
    SCRAPE_BACKOFF_BASE, SCRAPE_BACKOFF_MAX, SCRAPE_JITTER_MAX,
)

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]


class RateLimiter:
    """Per-domain rate limiter."""
    def __init__(self, rps: float = 1.5):
        self.min_interval = 1.0 / rps
        self._last_request: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, domain: str) -> asyncio.Lock:
        if domain not in self._locks:
            self._locks[domain] = asyncio.Lock()
        return self._locks[domain]

    async def acquire(self, domain: str):
        lock = self._get_lock(domain)
        async with lock:
            now = time.monotonic()
            last = self._last_request.get(domain, 0)
            wait = self.min_interval - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request[domain] = time.monotonic()


class HttpClient:
    """Shared async HTTP client with retry, backoff, and rate limiting."""
    def __init__(self, max_concurrency: int = SCRAPE_CONCURRENCY):
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.rate_limiter = RateLimiter()
        self._session: Optional[aiohttp.ClientSession] = None
        self._stats = {"requests": 0, "errors": 0, "retries": 0}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=SCRAPE_TIMEOUT)
            # Disable SSL verification for macOS cert issues (production should use proper certs)
            connector = aiohttp.TCPConnector(limit=50, limit_per_host=10, ssl=False)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    def _get_headers(self, url: str) -> dict:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    def _get_domain(self, url: str) -> str:
        from urllib.parse import urlparse
        return urlparse(url).netloc

    async def get(self, url: str, extra_headers: Optional[dict] = None,
                  retries: int = SCRAPE_MAX_RETRIES) -> Optional[str]:
        """Fetch URL with retry, backoff, and jitter. Returns HTML or None."""
        headers = self._get_headers(url)
        if extra_headers:
            headers.update(extra_headers)

        domain = self._get_domain(url)

        for attempt in range(retries + 1):
            try:
                async with self.semaphore:
                    await self.rate_limiter.acquire(domain)
                    session = await self._get_session()
                    self._stats["requests"] += 1

                    async with session.get(url, headers=headers, allow_redirects=True) as resp:
                        if resp.status == 200:
                            return await resp.text()
                        elif resp.status == 429:
                            retry_after = int(resp.headers.get("Retry-After", 5))
                            jitter = random.uniform(0, SCRAPE_JITTER_MAX)
                            wait = min(retry_after + jitter, SCRAPE_BACKOFF_MAX)
                            logger.warning(f"[429] {domain} - waiting {wait:.1f}s (attempt {attempt+1})")
                            await asyncio.sleep(wait)
                            self._stats["retries"] += 1
                        elif resp.status == 403:
                            logger.warning(f"[403] {domain} - blocked, not retrying")
                            self._stats["errors"] += 1
                            return None  # 403 is permanent, don't retry
                        elif resp.status == 404:
                            logger.debug(f"[404] {url}")
                            return None
                        else:
                            logger.warning(f"[{resp.status}] {url} (attempt {attempt+1})")
                            self._stats["errors"] += 1
                            if attempt < retries:
                                wait = min(SCRAPE_BACKOFF_BASE ** attempt + random.uniform(0, 1), SCRAPE_BACKOFF_MAX)
                                await asyncio.sleep(wait)

            except asyncio.TimeoutError:
                logger.warning(f"[TIMEOUT] {url} (attempt {attempt+1})")
                self._stats["errors"] += 1
                if attempt < retries:
                    await asyncio.sleep(SCRAPE_BACKOFF_BASE ** attempt)
            except aiohttp.ClientError as e:
                logger.warning(f"[CLIENT_ERROR] {url}: {e} (attempt {attempt+1})")
                self._stats["errors"] += 1
                if attempt < retries:
                    await asyncio.sleep(SCRAPE_BACKOFF_BASE ** attempt)
            except Exception as e:
                logger.error(f"[ERROR] {url}: {e}")
                self._stats["errors"] += 1
                return None

        return None

    async def get_json(self, url: str, extra_headers: Optional[dict] = None) -> Optional[dict]:
        """Fetch JSON endpoint."""
        headers = self._get_headers(url)
        headers["Accept"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)

        domain = self._get_domain(url)

        for attempt in range(SCRAPE_MAX_RETRIES + 1):
            try:
                async with self.semaphore:
                    await self.rate_limiter.acquire(domain)
                    session = await self._get_session()
                    self._stats["requests"] += 1

                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            return await resp.json(content_type=None)
                        elif resp.status == 429:
                            retry_after = int(resp.headers.get("Retry-After", 5))
                            await asyncio.sleep(retry_after + random.uniform(0, 1))
                            self._stats["retries"] += 1
                        else:
                            logger.warning(f"[{resp.status}] JSON: {url}")
                            return None
            except Exception as e:
                logger.warning(f"[ERROR] JSON {url}: {e} (attempt {attempt+1})")
                if attempt < SCRAPE_MAX_RETRIES:
                    await asyncio.sleep(SCRAPE_BACKOFF_BASE ** attempt)

        return None

    @property
    def stats(self) -> dict:
        return self._stats.copy()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
