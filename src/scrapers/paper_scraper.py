"""Research paper scraper — incremental ArXiv + Papers with Code + GitHub metrics.

Design goals:
- Incremental: never re-process papers already present in data/research_papers.json.
- ArXiv-safe: one request at a time, bounded retries, Retry-After support, no retry storm.
- No brute-force paper-page crawling for every ArXiv result.
- Papers with Code is used as a secondary source for code/GitHub evidence.
- GitHub stars are fetched only when a repository URL is explicitly available.
"""
import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
PWC_BASE = "https://paperswithcode.com"

ARXIV_BATCH_SIZE = 100
ARXIV_MIN_DELAY = 5
ARXIV_MAX_RETRIES = 3
ARXIV_BACKOFF = 30
ARXIV_MAX_PAGES = 60

DATA_FILE = Path("data/research_papers.json")


class PaperScraper(BaseScraper):
    """Incremental research-paper ingestion with bounded ArXiv retries."""

    async def scrape(self, target_count: int) -> list[dict]:
        existing_keys = self._load_existing_keys()

        self.logger.info(
            "PaperScraper: existing=%d, target_new=%d",
            len(existing_keys),
            target_count,
        )

        # ArXiv is the primary structured source.
        arxiv_records = await self._scrape_arxiv_api(
            target_count=target_count,
            existing_keys=existing_keys,
        )

        records = list(arxiv_records)

        # Papers with Code is only used if ArXiv did not provide enough NEW papers.
        remaining = target_count - len(records)
        if remaining > 0:
            pwc_records = await self._scrape_paperswithcode(
                target_count=remaining,
                existing_keys=existing_keys,
            )
            records.extend(pwc_records)

        # Final deduplication across sources.
        seen = set(existing_keys)
        unique: list[dict] = []

        for record in records:
            key = self._paper_key(record)
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(record)

        self.logger.info(
            "PaperScraper: new=%d, skipped_existing=%d",
            len(unique),
            max(0, len(records) - len(unique)),
        )

        return unique[:target_count]

    # ------------------------------------------------------------------
    # Existing-data / identity handling
    # ------------------------------------------------------------------

    def _load_existing_keys(self) -> set[str]:
        """Load canonical paper identities from the current JSON dataset."""
        if not DATA_FILE.exists():
            return set()

        try:
            with DATA_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                return set()

            keys = set()
            for record in data:
                key = self._paper_key(record)
                if key:
                    keys.add(key)

            return keys
        except Exception as exc:
            self.logger.warning("Could not load existing papers: %s", exc)
            return set()

    @staticmethod
    def _normalize_arxiv_id(value: str) -> str:
        """Return a stable ArXiv identifier from common URL/id formats."""
        if not value:
            return ""

        value = value.strip()

        # Examples:
        # http://arxiv.org/abs/2401.12345
        # https://export.arxiv.org/abs/2401.12345v2
        # 2401.12345v2
        match = re.search(r"(?:arxiv\.org/(?:abs|pdf)/|^)([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", value, re.I)
        if match:
            return match.group(1).lower()

        old_style = re.search(r"(?:arxiv\.org/(?:abs|pdf)/|^)([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", value, re.I)
        if old_style:
            return old_style.group(1).lower()

        return ""

    @classmethod
    def _paper_key(cls, record: dict) -> str:
        content = record.get("content", {}) if isinstance(record, dict) else {}
        paper_url = content.get("paper_url") or record.get("url") or ""

        arxiv_id = cls._normalize_arxiv_id(str(paper_url))
        if arxiv_id:
            return f"arxiv:{arxiv_id}"

        # PWC fallback: normalized URL identity.
        if paper_url:
            normalized = str(paper_url).strip().rstrip("/").lower()
            normalized = re.sub(r"^https?://", "", normalized)
            return f"url:{normalized}"

        title = re.sub(r"\s+", " ", str(content.get("title", "")).strip().lower())
        return f"title:{title}" if title else ""

    # ------------------------------------------------------------------
    # ArXiv
    # ------------------------------------------------------------------

    async def _scrape_arxiv_api(
        self,
        target_count: int,
        existing_keys: set[str],
    ) -> list[dict]:
        """Fetch newest ArXiv papers with bounded retries and no retry storm."""
        records: list[dict] = []
        seen = set(existing_keys)

        # One combined query is cheaper than four independent category loops.
        query = "(cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:cs.CV)"

        start = 0
        pages = 0

        while len(records) < target_count and pages < ARXIV_MAX_PAGES:
            params = {
                "search_query": query,
                "start": start,
                "max_results": ARXIV_BATCH_SIZE,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }

            xml_text = await self._arxiv_request(params)

            if xml_text is None:
                self.logger.warning(
                    "PaperScraper: ArXiv unavailable for this run; "
                    "continuing with Papers with Code."
                )
                break

            papers = self._parse_arxiv_xml(xml_text)
            if not papers:
                self.logger.info("PaperScraper: ArXiv returned no more papers.")
                break

            new_in_batch = 0

            for paper in papers:
                if len(records) >= target_count:
                    break

                key = self._paper_key(
                    {
                        "content": {
                            "paper_url": paper["url"],
                            "title": paper["title"],
                        }
                    }
                )

                if not key or key in seen:
                    continue

                seen.add(key)

                # Do not visit every ArXiv page. GitHub enrichment is handled
                # primarily by Papers with Code and only when a repo is known.
                record = {
                    "schemaVersion": "1.0",
                    "recordType": "RESEARCH_PAPER",
                    "source": {
                        "name": "ArXiv",
                        "url": paper["url"],
                    },
                    "content": {
                        "title": paper["title"],
                        "authors": paper["authors"],
                        "paper_url": paper["url"],
                        "github_url": None,
                        "github_stars": None,
                        "published_date": paper["published"],
                        "abstract": paper.get("abstract"),
                        "arxiv_id": self._normalize_arxiv_id(paper["url"]),
                    },
                    "collectedAt": datetime.now(timezone.utc).isoformat(),
                }

                records.append(record)
                new_in_batch += 1

            start += len(papers)
            pages += 1

            self.logger.info(
                "PaperScraper: ArXiv batch start=%d fetched=%d new=%d total_new=%d",
                start - len(papers),
                len(papers),
                new_in_batch,
                len(records),
            )

            # If fewer than the requested batch came back, there is no reason
            # to keep paging.
            if len(papers) < ARXIV_BATCH_SIZE:
                break

            await asyncio.sleep(ARXIV_MIN_DELAY)

        return records

    async def _arxiv_request(self, params: dict) -> Optional[str]:
        """Perform one ArXiv request with bounded retries.

        429 handling:
        - Respect Retry-After when provided.
        - Otherwise use 30s, 60s, 120s.
        - After 3 attempts, stop ArXiv for this run instead of retrying forever.
        """
        session = await self.http._get_session()

        for attempt in range(1, ARXIV_MAX_RETRIES + 1):
            try:
                # Important: ArXiv gets a dedicated concurrency gate of 1.
                # The global pipeline can still remain concurrent for other sources.
                async with session.get(
                    ARXIV_API,
                    params=params,
                    headers={
                        "User-Agent": "AI-Signal-Research-Pipeline/1.0 (contact: data-engineering)",
                        "Accept": "application/atom+xml",
                    },
                ) as resp:
                    if resp.status == 200:
                        return await resp.text()

                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        try:
                            wait = max(ARXIV_BACKOFF, int(retry_after))
                        except (TypeError, ValueError):
                            wait = ARXIV_BACKOFF * (2 ** (attempt - 1))

                        if attempt >= ARXIV_MAX_RETRIES:
                            self.logger.warning(
                                "ArXiv rate limited after %d attempts; "
                                "stopping ArXiv for this run.",
                                attempt,
                            )
                            return None

                        self.logger.warning(
                            "ArXiv rate limited (attempt %d/%d); waiting %ss...",
                            attempt,
                            ARXIV_MAX_RETRIES,
                            wait,
                        )
                        await asyncio.sleep(wait)
                        continue

                    if resp.status in {403, 404}:
                        self.logger.warning(
                            "ArXiv returned HTTP %d; stopping ArXiv for this run.",
                            resp.status,
                        )
                        return None

                    self.logger.warning(
                        "ArXiv API returned HTTP %d (attempt %d/%d)",
                        resp.status,
                        attempt,
                        ARXIV_MAX_RETRIES,
                    )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt >= ARXIV_MAX_RETRIES:
                    self.logger.warning(
                        "ArXiv request failed after %d attempts: %s",
                        attempt,
                        exc,
                    )
                    return None

                wait = min(ARXIV_BACKOFF * attempt, 120)
                self.logger.warning(
                    "ArXiv request error (attempt %d/%d): %s; "
                    "waiting %ss...",
                    attempt,
                    ARXIV_MAX_RETRIES,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)

        return None

    def _parse_arxiv_xml(self, xml_text: str) -> list[dict]:
        """Parse ArXiv Atom XML response."""
        papers: list[dict] = []

        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                title = entry.findtext("atom:title", "", ns).strip()
                title = re.sub(r"\s+", " ", title)

                authors = []
                for author in entry.findall("atom:author", ns):
                    name = author.findtext("atom:name", "", ns).strip()
                    if name:
                        authors.append(name)

                paper_url = ""
                for link in entry.findall("atom:link", ns):
                    if link.get("title") == "pdf":
                        continue
                    href = link.get("href", "")
                    if "/abs/" in href:
                        paper_url = href
                        break

                if not paper_url:
                    paper_url = entry.findtext("atom:id", "", ns).strip()

                published = entry.findtext("atom:published", "", ns).strip()

                abstract = entry.findtext("atom:summary", "", ns).strip()
                abstract = re.sub(r"\s+", " ", abstract)

                if title and paper_url:
                    papers.append(
                        {
                            "title": title,
                            "authors": authors,
                            "url": paper_url,
                            "published": published,
                            "abstract": abstract[:2000],
                        }
                    )

        except ET.ParseError as exc:
            self.logger.warning("ArXiv XML parse error: %s", exc)

        return papers

    # ------------------------------------------------------------------
    # Papers with Code
    # ------------------------------------------------------------------

    async def _scrape_paperswithcode(
        self,
        target_count: int,
        existing_keys: set[str],
    ) -> list[dict]:
        """Use Papers with Code as a secondary source for GitHub-linked papers."""
        records: list[dict] = []
        seen = set(existing_keys)
        page = 1

        while len(records) < target_count and page <= 50:
            url = f"{PWC_BASE}/?page={page}"
            soup = await self.fetch_and_parse(url)

            if not soup:
                self.logger.warning("Papers with Code unavailable at page %d", page)
                break

            paper_rows = soup.select(
                "div.col-md-12, tr, div.paper-card, article"
            )
            if not paper_rows:
                paper_rows = soup.select("a[href*='/paper/']")

            if not paper_rows:
                self.logger.info(
                    "Papers with Code: no more papers at page %d", page
                )
                break

            page_new = 0

            for row in paper_rows:
                if len(records) >= target_count:
                    break

                title_link = (
                    row.select_one("a[href*='/paper/']")
                    or row.select_one("h1 a, h2 a, h3 a")
                )
                if not title_link:
                    continue

                title = self.extract_text(title_link)
                href = self.extract_attribute(title_link, "href")

                if not title or not href:
                    continue

                paper_url = (
                    f"{PWC_BASE}{href}" if href.startswith("/") else href
                )

                key = self._paper_key(
                    {"content": {"paper_url": paper_url, "title": title}}
                )
                if not key or key in seen:
                    continue

                authors_el = row.select_one(
                    ".authors, .paper-authors, small, span.authors"
                )
                authors_text = (
                    self.extract_text(authors_el) if authors_el else ""
                )
                authors = (
                    [a.strip() for a in re.split(r",|&", authors_text) if a.strip()]
                    if authors_text
                    else []
                )

                github_el = row.select_one("a[href*='github.com']")
                github_url = (
                    self.extract_attribute(github_el, "href")
                    if github_el
                    else None
                )

                github_stars = None
                if github_url:
                    github_stars = await self._get_github_stars(github_url)

                date_el = row.select_one("time, .date, span[title]")
                published = None
                if date_el:
                    published = (
                        self.extract_attribute(date_el, "datetime")
                        or self.extract_text(date_el)
                    )

                record = {
                    "schemaVersion": "1.0",
                    "recordType": "RESEARCH_PAPER",
                    "source": {
                        "name": "Papers with Code",
                        "url": paper_url,
                    },
                    "content": {
                        "title": title,
                        "authors": authors,
                        "paper_url": paper_url,
                        "github_url": github_url,
                        "github_stars": github_stars,
                        "published_date": published,
                        "abstract": None,
                    },
                    "collectedAt": datetime.now(timezone.utc).isoformat(),
                }

                seen.add(key)
                records.append(record)
                page_new += 1

            self.logger.info(
                "PaperScraper: PWC page=%d new=%d total_new=%d",
                page,
                page_new,
                len(records),
            )

            page += 1
            await asyncio.sleep(2)

        return records[:target_count]

    # ------------------------------------------------------------------
    # GitHub metrics
    # ------------------------------------------------------------------

    async def _get_github_stars(self, github_url: str) -> Optional[int]:
        """Get current GitHub star count; fail fast on blocked/invalid repos."""
        parsed = urlparse(github_url)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            return None

        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            return None

        owner, repo = parts[0], parts[1]
        repo = repo.removesuffix(".git")

        api_url = f"https://api.github.com/repos/{owner}/{repo}"

        try:
            session = await self.http._get_session()
            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": "AI-Signal-Research-Pipeline/1.0",
            }

            async with session.get(api_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return data.get("stargazers_count")

                # Never hammer GitHub on auth/rate-limit/not-found responses.
                if resp.status in {403, 404, 429}:
                    return None

        except asyncio.CancelledError:
            raise
        except Exception:
            return None

        return None
