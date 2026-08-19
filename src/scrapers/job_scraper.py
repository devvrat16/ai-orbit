"""AI job scraper — extracts 24-hour fresh jobs from AI job boards."""
import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional
from src.scrapers.base import BaseScraper
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)

ROLE_FAMILIES = {
    "engineer": "Engineering", "developer": "Engineering", "software": "Engineering",
    "ml": "Machine Learning", "machine learning": "Machine Learning", "deep learning": "Machine Learning",
    "ai": "Artificial Intelligence", "data scientist": "Data Science", "data analyst": "Data Science",
    "research": "Research", "scientist": "Research",
    "product": "Product", "design": "Design", "manager": "Management", "lead": "Management",
    "devops": "Infrastructure", "sre": "Infrastructure", "infrastructure": "Infrastructure",
    "security": "Security", "nlp": "NLP", "computer vision": "Computer Vision",
}


class JobScraper(BaseScraper):
    """Scrapes AI jobs from multiple sources, filtering to last 24 hours."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.freshness_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    async def scrape(self, target_count: int = 200) -> list[dict]:
        records = []

        # Run all sources concurrently for maximum throughput
        tasks = [
            self._scrape_remoteok_api(),
            self._scrape_ynab_hackernews(),
            self._scrape_aijobs_net(),
            self._scrape_builtin(),
            self._scrape_arbeitnow(),
            self._scrape_simplify_jobs(),
            self._scrape_findwork(),
            self._scrape_arbeitnow_ai(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                records.extend(result)
            elif isinstance(result, Exception):
                self.logger.error(f"Job source error: {result}")

        # Deduplicate by URL or title+company
        records = self._deduplicate_jobs(records)

        self.logger.info(f"Job Scraper: {len(records)} fresh jobs collected")
        return records

    def _deduplicate_jobs(self, records: list[dict]) -> list[dict]:
        """Deduplicate jobs by URL or title+company combo."""
        seen = set()
        unique = []
        for r in records:
            content = r.get("content", {})
            url = content.get("url", "")
            title_company = f"{content.get('title', '')}|{content.get('company', '')}".lower()

            key = url if url else title_company
            if key and key not in seen:
                seen.add(key)
                unique.append(r)
        return unique

    # ==================================================================
    #  RemoteOK API — JSON endpoint, no Cloudflare
    # ==================================================================
    async def _scrape_remoteok_api(self) -> list[dict]:
        """Scrape RemoteOK via their public JSON API."""
        records = []
        try:
            session = await self.http._get_session()
            headers = {
                "Accept": "application/json",
                "User-Agent": "GraphOne-Pipeline/1.0",
            }
            async with session.get("https://remoteok.com/api", headers=headers) as resp:
                if resp.status != 200:
                    self.logger.warning(f"RemoteOK API returned {resp.status}")
                    return records
                data = await resp.json(content_type=None)
        except Exception as e:
            self.logger.warning(f"RemoteOK API error: {e}")
            return records

        if not isinstance(data, list):
            return records

        # First item is metadata, skip it
        for job in data:
            if not isinstance(job, dict) or "id" not in job:
                continue

            # Filter for AI/ML keywords
            title = job.get("position", "")
            tags = job.get("tags", []) or []
            description = job.get("description", "")
            combined = f"{title} {' '.join(tags)} {description}".lower()

            ai_keywords = ["ai", "machine learning", "ml", "deep learning", "nlp",
                          "data science", "artificial intelligence", "llm", "neural",
                          "computer vision", "nlp", "generative"]
            if not any(kw in combined for kw in ai_keywords):
                continue

            # Check date freshness
            job_date = None
            date_val = job.get("date", "")
            if date_val:
                try:
                    job_date = dateparser.parse(date_val)
                    if job_date and job_date.tzinfo is None:
                        job_date = job_date.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            # Include if fresh OR if date is unknown (many boards strip dates)
            if job_date and job_date < self.freshness_cutoff:
                continue

            company = job.get("company", "Unknown")
            job_url = job.get("url", f"https://remoteok.com/remote-jobs/{job.get('id', '')}")
            location = job.get("location", "Remote")

            record = {
                "schemaVersion": "1.0",
                "recordType": "JOB",
                "source": {"name": "RemoteOK", "url": job_url},
                "content": {
                    "company": company,
                    "title": title,
                    "date": job_date.isoformat() if job_date else datetime.now(timezone.utc).isoformat(),
                    "is_remote": True,
                    "role_family": self._classify_role(title),
                    "location": location,
                    "url": job_url,
                },
                "collectedAt": datetime.utcnow().isoformat() + "Z",
            }
            records.append(record)

        self.logger.info(f"RemoteOK: {len(records)} AI/ML jobs")
        return records

    # ==================================================================
    #  Hacker News "Who is Hiring" — parse monthly threads
    # ==================================================================
    async def _scrape_ynab_hackernews(self) -> list[dict]:
        """Scrape Hacker News 'Who is Hiring' monthly threads via Algolia API."""
        records = []

        # Search for recent "Ask HN: Who is hiring?" threads
        try:
            session = await self.http._get_session()
            # Get recent "who is hiring" stories from Algolia
            url = "https://hn.algolia.com/api/v1/search?query=%22Ask%20HN%3A%20Who%20is%20hiring%22&tags=ask_hn&hitsPerPage=5"
            async with session.get(url) as resp:
                if resp.status != 200:
                    self.logger.warning(f"HN Algolia returned {resp.status}")
                    return records
                data = await resp.json(content_type=None)
        except Exception as e:
            self.logger.warning(f"HN search error: {e}")
            return records

        hits = data.get("hits", [])
        if not hits:
            return records

        # Get the most recent thread
        thread = hits[0]
        thread_id = thread.get("objectID")
        if not thread_id:
            return records

        # Fetch comments (job postings) from the thread
        try:
            session = await self.http._get_session()
            url = f"https://hn.algolia.com/api/v1/items/{thread_id}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return records
                item_data = await resp.json(content_type=None)
        except Exception as e:
            self.logger.warning(f"HN thread error: {e}")
            return records

        children = item_data.get("children", [])
        self.logger.info(f"HN Who is Hiring: {len(children)} top-level comments")

        for child in children[:200]:  # Process up to 200 postings
            text = child.get("text", "")
            if not text or len(text) < 20:
                continue

            # Filter for AI/ML jobs
            text_lower = text.lower()
            ai_keywords = ["ai", "machine learning", "ml", "deep learning", "nlp",
                          "data science", "artificial intelligence", "llm", "neural",
                          "computer vision", "generative", "gpt", "transformer"]
            if not any(kw in text_lower for kw in ai_keywords):
                continue

            # Extract company name (usually first line, before first |)
            lines = text.split("<p>")
            first_line = re.sub(r'<[^>]+>', '', lines[0]).strip()
            parts = first_line.split("|")
            company = parts[0].strip() if parts else "Unknown"
            # Clean HTML from company name
            company = re.sub(r'<[^>]+>', '', company).strip()
            if len(company) > 60:
                company = company[:60]

            # Extract role/title from first meaningful text
            title_match = re.search(r'(?:looking for|hiring|role|position)[:\s]*([^<.\n]+)', text_lower)
            title = title_match.group(1).strip().title() if title_match else "AI/ML Role"

            # Check if remote
            is_remote = any(term in text_lower for term in ["remote", "work from home", "wfh", "distributed", "anywhere"])

            # HN post date
            post_date = child.get("created_at", "")
            job_date = None
            if post_date:
                try:
                    job_date = dateparser.parse(post_date)
                except Exception:
                    pass

            job_url = f"https://news.ycombinator.com/item?id={thread_id}"

            record = {
                "schemaVersion": "1.0",
                "recordType": "JOB",
                "source": {"name": "HackerNews Who's Hiring", "url": job_url},
                "content": {
                    "company": company,
                    "title": title,
                    "date": job_date.isoformat() if job_date else datetime.now(timezone.utc).isoformat(),
                    "is_remote": is_remote,
                    "role_family": self._classify_role(title),
                    "location": "See posting",
                    "url": job_url,
                },
                "collectedAt": datetime.utcnow().isoformat() + "Z",
            }
            records.append(record)

        self.logger.info(f"HN Who's Hiring: {len(records)} AI/ML jobs")
        return records

    # ==================================================================
    #  AIJobs.net — simple HTML, no Cloudflare
    # ==================================================================
    async def _scrape_aijobs_net(self) -> list[dict]:
        """Scrape AIJobs.net for AI-specific job listings."""
        records = []

        pages_to_try = [
            "https://aijobs.net/",
            "https://aijobs.net/jobs/",
            "https://aijobs.net/?page=1",
            "https://aijobs.net/jobs/?page=1",
        ]

        for page_url in pages_to_try:
            if records:
                break
            soup = await self.fetch_and_parse(page_url)
            if not soup:
                continue

            # AIJobs.net uses various card layouts
            job_cards = soup.select(
                "div.job-card, div.job-item, article, "
                "div[class*='job'], div[class*='listing'], "
                "tr, li.job"
            )

            if not job_cards:
                # Try broader selectors
                job_cards = soup.select("a[href*='/jobs/'], a[href*='/job/']")

            self.logger.info(f"AIJobs.net: found {len(job_cards)} elements at {page_url}")

            for card in job_cards[:100]:
                if len(records) >= 100:
                    break
                record = self._parse_job_card(card, "AIJobs.net", "https://aijobs.net")
                if record:
                    records.append(record)

            if records:
                break
            await asyncio.sleep(0.5)

        self.logger.info(f"AIJobs.net: {len(records)} jobs")
        return records

    # ==================================================================
    #  BuiltIn — already partially works
    # ==================================================================
    async def _scrape_builtin(self) -> list[dict]:
        """Scrape BuiltIn AI/ML jobs."""
        records = []
        urls = [
            "https://builtin.com/jobs/machine-learning-ai",
            "https://builtin.com/jobs/artificial-intelligence",
            "https://builtin.com/jobs/data-science",
        ]

        for url in urls:
            soup = await self.fetch_and_parse(url)
            if not soup:
                continue

            # BuiltIn job cards
            cards = soup.select(
                "div.job-card, article.job, div[class*='job-listing'], "
                "div[class*='card'], div[data-job-id]"
            )
            if not cards:
                cards = soup.select("a[href*='/jobs/']")

            self.logger.info(f"BuiltIn: found {len(cards)} job elements at {url}")

            for card in cards[:50]:
                if len(records) >= 50:
                    break
                record = self._parse_job_card(card, "Built In", "https://builtin.com")
                if record:
                    records.append(record)

            await asyncio.sleep(0.5)

        self.logger.info(f"BuiltIn: {len(records)} jobs")
        return records

    # ==================================================================
    #  Arbeitnow — public API, no Cloudflare
    # ==================================================================
    async def _scrape_arbeitnow(self) -> list[dict]:
        """Scrape Arbeitnow API for remote AI jobs."""
        records = []
        try:
            session = await self.http._get_session()
            url = "https://www.arbeitnow.com/api/job-board-api"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return records
                data = await resp.json(content_type=None)
        except Exception as e:
            self.logger.warning(f"Arbeitnow API error: {e}")
            return records

        jobs = data.get("data", [])
        for job in jobs:
            title = job.get("title", "")
            tags = job.get("tags", []) or []
            description = job.get("description", "")
            combined = f"{title} {' '.join(tags)} {description}".lower()

            ai_keywords = ["ai", "machine learning", "ml", "deep learning", "nlp",
                          "data science", "artificial intelligence", "llm", "neural"]
            if not any(kw in combined for kw in ai_keywords):
                continue

            # Check date
            job_date = None
            date_str = job.get("created_at", "")
            if date_str:
                try:
                    job_date = dateparser.parse(date_str)
                    if job_date and job_date.tzinfo is None:
                        job_date = job_date.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            if job_date and job_date < self.freshness_cutoff:
                continue

            company = job.get("company_name", "Unknown")
            job_url = job.get("url", job.get("apply_url", ""))
            location = job.get("location", "")

            record = {
                "schemaVersion": "1.0",
                "recordType": "JOB",
                "source": {"name": "Arbeitnow", "url": job_url},
                "content": {
                    "company": company,
                    "title": title,
                    "date": job_date.isoformat() if job_date else datetime.now(timezone.utc).isoformat(),
                    "is_remote": job.get("remote", False),
                    "role_family": self._classify_role(title),
                    "location": location,
                    "url": job_url,
                },
                "collectedAt": datetime.utcnow().isoformat() + "Z",
            }
            records.append(record)

        self.logger.info(f"Arbeitnow: {len(records)} AI/ML jobs")
        return records

    # ==================================================================
    #  Simplify Jobs — public JSON, no Cloudflare
    # ==================================================================
    async def _scrape_simplify_jobs(self) -> list[dict]:
        """Scrape Simplify job listings API."""
        records = []
        try:
            session = await self.http._get_session()
            # Simplify has a public jobs API
            url = "https://api.simplify.jobs/v2/jobs?query=AI+machine+learning&limit=100"
            headers = {"Accept": "application/json", "User-Agent": "GraphOne-Pipeline/1.0"}
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    self.logger.info(f"Simplify API returned {resp.status}")
                    return records
                data = await resp.json(content_type=None)
        except Exception as e:
            self.logger.debug(f"Simplify API error: {e}")
            return records

        jobs = data if isinstance(data, list) else data.get("jobs", data.get("data", []))
        if not isinstance(jobs, list):
            return records

        for job in jobs:
            if not isinstance(job, dict):
                continue

            title = job.get("title", job.get("name", ""))
            company = job.get("company", "")
            if isinstance(company, dict):
                company = company.get("name", "")

            if not title:
                continue

            job_url = job.get("url", job.get("apply_url", job.get("link", "")))

            record = {
                "schemaVersion": "1.0",
                "recordType": "JOB",
                "source": {"name": "Simplify", "url": job_url},
                "content": {
                    "company": company or "Unknown",
                    "title": title,
                    "date": datetime.now(timezone.utc).isoformat(),
                    "is_remote": bool(job.get("remote", False)),
                    "role_family": self._classify_role(title),
                    "location": job.get("location", ""),
                    "url": job_url,
                },
                "collectedAt": datetime.utcnow().isoformat() + "Z",
            }
            records.append(record)

        self.logger.info(f"Simplify: {len(records)} jobs")
        return records

    # ==================================================================
    #  Findwork.dev API — public JSON, tech jobs
    # ==================================================================
    async def _scrape_findwork(self) -> list[dict]:
        """Scrape findwork.dev public API for tech/AI jobs."""
        records = []
        try:
            session = await self.http._get_session()
            url = "https://findwork.dev/api/jobs/?search=AI+machine+learning&order_by=-date_posted"
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    self.logger.info(f"Findwork API returned {resp.status}")
                    return records
                data = await resp.json(content_type=None)
        except Exception as e:
            self.logger.debug(f"Findwork API error: {e}")
            return records

        results = data.get("results", []) if isinstance(data, dict) else data
        if not isinstance(results, list):
            return records

        for job in results:
            if not isinstance(job, dict):
                continue
            title = job.get("role", "")
            company = job.get("company_name", "")
            if not title:
                continue

            job_url = job.get("url", job.get("apply_url", ""))

            record = {
                "schemaVersion": "1.0",
                "recordType": "JOB",
                "source": {"name": "Findwork", "url": job_url},
                "content": {
                    "company": company or "Unknown",
                    "title": title,
                    "date": job.get("date_posted", datetime.now(timezone.utc).isoformat()),
                    "is_remote": bool(job.get("remote", False)),
                    "role_family": self._classify_role(title),
                    "location": job.get("location", ""),
                    "url": job_url,
                },
                "collectedAt": datetime.utcnow().isoformat() + "Z",
            }
            records.append(record)

        self.logger.info(f"Findwork: {len(records)} jobs")
        return records

    # ==================================================================
    #  Arbeitnow AI filter — second pass with broader AI keywords
    # ==================================================================
    async def _scrape_arbeitnow_ai(self) -> list[dict]:
        """Scrape Arbeitnow for AI-specific roles using keyword search."""
        records = []
        page = 1
        max_pages = 10

        while len(records) < 100 and page <= max_pages:
            url = f"https://www.arbeitnow.com/api/job-board-api?page={page}"
            try:
                data = await self.http.get_json(url)
                if not data:
                    break
            except Exception:
                break

            jobs = data.get("data", [])
            if not jobs:
                break

            for job in jobs:
                if not isinstance(job, dict):
                    continue

                title = job.get("title", "")
                company = job.get("company_name", "")
                desc = (job.get("description", "") or "").lower()
                title_lower = title.lower()

                # Only AI/ML specific
                ai_kw = ["ai", "machine learning", "ml engineer", "deep learning",
                         "nlp", "data scientist", "llm", "computer vision",
                         "artificial intelligence", "neural", "generative"]
                if not any(kw in title_lower or kw in desc for kw in ai_kw):
                    continue

                job_url = job.get("url", "")
                tags = job.get("tags", [])

                record = {
                    "schemaVersion": "1.0",
                    "recordType": "JOB",
                    "source": {"name": "Arbeitnow AI", "url": job_url},
                    "content": {
                        "company": company or "Unknown",
                        "title": title,
                        "date": job.get("created_at", datetime.now(timezone.utc).isoformat()),
                        "is_remote": bool(job.get("remote", False)),
                        "role_family": self._classify_role(title),
                        "location": job.get("location", ""),
                        "url": job_url,
                    },
                    "collectedAt": datetime.utcnow().isoformat() + "Z",
                }
                records.append(record)

            page += 1
            await asyncio.sleep(0.5)

        self.logger.info(f"Arbeitnow AI: {len(records)} AI-specific jobs")
        return records

    # ==================================================================
    #  Shared: card parser + role classifier + date parser
    # ==================================================================
    def _parse_job_card(self, card, source_name: str, base_url: str) -> Optional[dict]:
        """Parse a generic job card into a record."""
        # Extract title
        title = None
        job_url = None
        for selector in ["h2 a", "h3 a", "h4 a", ".job-title a", "a[href*='/jobs/']", "a[href*='/job/']", "a"]:
            el = card.select_one(selector)
            if el:
                title = self.extract_text(el)
                href = self.extract_attribute(el, "href")
                if href:
                    job_url = href if href.startswith("http") else base_url.rstrip("/") + "/" + href.lstrip("/")
                if title and len(title) >= 3:
                    break

        if not title:
            title = self.extract_text(card.select_one("h2, h3, h4, .title, strong"))
        if not title or len(title) < 3:
            return None

        # Extract company
        company = None
        for selector in [".company-name", ".company", "span.companyName", ".job-company",
                         "a[class*='company']", ".employer", ".org"]:
            el = card.select_one(selector)
            if el:
                company = self.extract_text(el)
                if company:
                    break

        if not company:
            card_text = card.get_text(strip=True)
            parts = re.split(r'[·|•–—]', card_text)
            if len(parts) > 1:
                company = parts[0].strip()[:60]

        if not company:
            company = "Unknown Company"

        # Extract location
        location = None
        for selector in [".location", ".job-location", "span.location", ".companyLocation", ".loc"]:
            el = card.select_one(selector)
            if el:
                location = self.extract_text(el)
                if location:
                    break

        # Remote detection
        combined = f"{title} {location or ''} {card.get_text(strip=True)[:200]}".lower()
        is_remote = any(term in combined for term in ["remote", "work from home", "wfh", "distributed", "anywhere"])

        # Date
        job_date = None
        for selector in [".date", "time", ".posted", ".new", "span.date", ".age"]:
            el = card.select_one(selector)
            if el:
                dt_attr = el.get("datetime")
                if dt_attr:
                    job_date = self._parse_date(dt_attr)
                else:
                    text = self.extract_text(el)
                    if text:
                        job_date = self._parse_date(text)
                if job_date:
                    break

        # Freshness check
        if job_date and job_date < self.freshness_cutoff:
            return None

        role_family = self._classify_role(title)

        return {
            "schemaVersion": "1.0",
            "recordType": "JOB",
            "source": {"name": source_name, "url": job_url or base_url},
            "content": {
                "company": company,
                "title": title,
                "date": job_date.isoformat() if job_date else datetime.now(timezone.utc).isoformat(),
                "is_remote": is_remote,
                "role_family": role_family,
                "location": location,
                "url": job_url,
            },
            "collectedAt": datetime.utcnow().isoformat() + "Z",
        }

    def _classify_role(self, title: str) -> str:
        title_lower = title.lower()
        for keyword, family in sorted(ROLE_FAMILIES.items(), key=lambda x: -len(x[0])):
            if keyword in title_lower:
                return family
        return "Other"

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            dt = dateparser.parse(date_str)
            if dt:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
        except (ValueError, TypeError):
            pass

        now = datetime.now(timezone.utc)
        date_lower = date_str.lower().strip()

        match = re.search(r'(\d+)\s*(minute|hour|day|week)s?\s*ago', date_lower)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            deltas = {"minute": timedelta(minutes=num), "hour": timedelta(hours=num),
                      "day": timedelta(days=num), "week": timedelta(weeks=num)}
            return now - deltas.get(unit, timedelta())

        if "yesterday" in date_lower:
            return now - timedelta(days=1)
        if "today" in date_lower:
            return now

        return None
