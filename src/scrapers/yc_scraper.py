"""Y Combinator company scraper — extracts startups from yc.com/companies."""
import asyncio
import json
import logging
from datetime import datetime
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

YC_URL = "https://www.ycombinator.com/companies"
YC_API_URL = "https://api.ycombinator.com/v0.1/companies"


class YCScraper(BaseScraper):
    """Scrapes startups from Y Combinator's public company directory."""

    async def scrape(self, target_count: int) -> list[dict]:
        records = []

        # Use YC's public JSON API
        api_records = await self._scrape_api(target_count)
        records.extend(api_records)

        # Supplement with HTML scraping if needed
        if len(records) < target_count:
            html_records = await self._scrape_html(target_count - len(records))
            records.extend(html_records)

        # Deduplicate by company name
        seen = set()
        unique = []
        for r in records:
            name = r.get("content", {}).get("entityName", "").lower().strip()
            if name and name not in seen:
                seen.add(name)
                unique.append(r)

        self.logger.info(f"YC Scraper: {len(unique)} unique startups collected")
        return unique[:target_count]

    async def _scrape_api(self, target_count: int) -> list[dict]:
        """Query YC's public JSON API for company data."""
        records = []
        page_size = 25  # YC API returns ~25 per page regardless of request
        max_pages = min((target_count // page_size) + 20, 120)  # extra buffer to ensure we hit target

        for page in range(1, max_pages + 1):
            if len(records) >= target_count:
                break

            url = f"{YC_API_URL}?page={page}&per_page={page_size}"
            data = await self.fetch_json(url)

            if not data:
                self.logger.warning(f"YC API returned no data at page {page}")
                break

            companies = data.get("companies", [])
            if not companies:
                self.logger.info(f"YC API: no more companies at page {page}")
                break

            for company in companies:
                name = company.get("name", "").strip()
                if not name:
                    continue

                slug = company.get("slug", "")
                company_url = company.get("url", f"https://www.ycombinator.com/companies/{slug}")

                # Parse location from locations array
                locations = company.get("locations", [])
                location = ", ".join(locations) if locations else ""

                # Parse industry from tags
                tags = company.get("tags", [])
                industries = [t for t in tags if t not in ["B2B", "B2C", "Enterprise", "Consumer"]]
                industry = ", ".join(industries) if industries else ""

                record = {
                    "schemaVersion": "1.0",
                    "recordType": "STARTUP",
                    "source": {
                        "name": "Y Combinator",
                        "url": company_url,
                    },
                    "content": {
                        "entityName": name,
                        "employeeCount": company.get("teamSize"),
                        "description": company.get("oneLiner", "") or company.get("longDescription", "")[:200],
                        "website": company.get("website", ""),
                        "location": location,
                        "industry": industry,
                        "founded_year": None,
                    },
                    "collectedAt": datetime.utcnow().isoformat() + "Z",
                }
                records.append(record)

                if len(records) >= target_count:
                    break

            self.logger.info(f"YC API page {page}: {len(companies)} companies, total: {len(records)}")
            await asyncio.sleep(0.2)

        return records

    async def _scrape_html(self, target_count: int) -> list[dict]:
        """Fallback: scrape YC companies page HTML."""
        records = []
        page = 0

        while len(records) < target_count and page < 20:
            url = f"{YC_URL}?page={page}"
            soup = await self.fetch_and_parse(url)
            if not soup:
                break

            company_links = soup.select("a[href*='/companies/']")
            if not company_links:
                break

            for link in company_links:
                href = link.get("href", "")
                if "/companies/" not in href or href.count("/") < 3:
                    continue

                name = self.extract_text(link)
                if not name or len(name) < 2:
                    continue

                full_url = f"https://www.ycombinator.com{href}" if href.startswith("/") else href

                record = {
                    "schemaVersion": "1.0",
                    "recordType": "STARTUP",
                    "source": {"name": "Y Combinator", "url": full_url},
                    "content": {
                        "entityName": name,
                        "employeeCount": None,
                        "description": None,
                        "website": None,
                        "location": None,
                        "industry": None,
                        "founded_year": None,
                    },
                    "collectedAt": datetime.utcnow().isoformat() + "Z",
                }
                records.append(record)

                if len(records) >= target_count:
                    break

            page += 1
            await asyncio.sleep(0.5)

        return records
