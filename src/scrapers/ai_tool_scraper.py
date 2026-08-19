"""AI tool/product directory scraper — extracts products from multiple sources."""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Futurepedia constants
# ---------------------------------------------------------------------------
FUTUREPEDIA_BASE = "https://futurepedia.io"
FUTUREPEDIA_CATEGORIES = [
    "/ai-tools/productivity",
    "/ai-tools/ai-agents",
    "/ai-tools/image-generators",
    "/ai-tools/text-generators",
    "/ai-tools/video-generators",
    "/ai-tools/chatbots",
    "/ai-tools/code-assistant",
    "/ai-tools/marketing",
    "/ai-tools/writing-generators",
    "/ai-tools/social-media",
    "/ai-tools/finance",
    "/ai-tools/business",
    "/ai-tools/design-generators",
    "/ai-tools/music-generator",
    "/ai-tools/audio-generators",
    "/ai-tools/3D-generator",
    "/ai-tools/video-editing",
    "/ai-tools/image-editing",
    "/ai-tools/text-to-speech",
    "/ai-tools/text-to-video",
    "/ai-tools/text-to-image",
    "/ai-tools/website-builders",
    "/ai-tools/project-management",
    "/ai-tools/automations",
    "/ai-tools/workflows",
    "/ai-tools/research-assistant",
    "/ai-tools/personal-assistant",
    "/ai-tools/copywriting-assistant",
    "/ai-tools/paraphrasing",
    "/ai-tools/storyteller",
    "/ai-tools/prompt-generators",
    "/ai-tools/spreadsheet-assistant",
    "/ai-tools/translators",
    "/ai-tools/presentations",
    "/ai-tools/video-enhancer",
    "/ai-tools/cartoon-generators",
    "/ai-tools/portrait-generators",
    "/ai-tools/avatar-generator",
    "/ai-tools/logo-generator",
    "/ai-tools/art",
    "/ai-tools/audio-editing",
    "/ai-tools/transcriber",
    "/ai-tools/fitness",
    "/ai-tools/students",
    "/ai-tools/misc-tools",
    "/ai-tools/no-code",
    "/ai-tools/sql-assistant",
    "/ai-tools/code",
    "/ai-tools/religion",
    "/ai-tools/fashion-assistant",
    "/ai-tools/gift-ideas",
]

# ---------------------------------------------------------------------------
# ToolPilot constants
# ---------------------------------------------------------------------------
TOOLPILOT_BASE = "https://www.toolpilot.ai"
TOOLPILOT_COLLECTIONS = [
    "/collections/all",
    "/collections/text-content",
    "/collections/images-photos",
    "/collections/video-3d",
    "/collections/art-animation",
    "/collections/marketing",
    "/collections/social-media",
    "/collections/chat-chatbots",
    "/collections/coding-development",
    "/collections/seo",
    "/collections/business-office",
    "/collections/education",
    "/collections/email-communication",
    "/collections/music-audio",
    "/collections/web-design-tools",
    "/collections/e-commerce-shopping",
    "/collections/automation-macros",
    "/collections/tiktok",
    "/collections/free-ai-tools",
]

# ---------------------------------------------------------------------------
# TAAFT constants
# ---------------------------------------------------------------------------
TAAFT_BASE = "https://theresanaiforthat.com"


class AIToolScraper(BaseScraper):
    """Scrapes AI products/tools from directory sites."""

    SOURCES = [
        {"name": "Futurepedia", "base_url": FUTUREPEDIA_BASE, "type": "futurepedia"},
        {"name": "ToolPilot", "base_url": TOOLPILOT_BASE, "type": "toolpilot"},
        {"name": "There's An AI For That", "base_url": TAAFT_BASE, "type": "taaft"},
    ]

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    async def scrape(self, target_count: int) -> list[dict]:
        records: list[dict] = []

        # Run Futurepedia, ToolPilot, and TopAI in parallel (all use aiohttp)
        fp_task = asyncio.create_task(self._scrape_futurepedia(target_count))
        tp_task = asyncio.create_task(self._scrape_toolpilot(target_count))
        topai_task = asyncio.create_task(self._scrape_topai(target_count))

        fp_result, tp_result, topai_result = await asyncio.gather(
            fp_task, tp_task, topai_task, return_exceptions=True
        )

        if isinstance(fp_result, list):
            records.extend(fp_result)
        elif isinstance(fp_result, Exception):
            self.logger.error(f"Futurepedia error: {fp_result}")

        if isinstance(tp_result, list):
            records.extend(tp_result)
        elif isinstance(tp_result, Exception):
            self.logger.error(f"ToolPilot error: {tp_result}")

        if isinstance(topai_result, list):
            records.extend(topai_result)
        elif isinstance(topai_result, Exception):
            self.logger.error(f"TopAI error: {topai_result}")

        # TAAFT via cloudscraper (sync in thread pool)
        taaft_records = await self._scrape_taaft()
        records.extend(taaft_records)

        # Deduplicate by product name
        records = self._deduplicate(records)

        self.logger.info(
            f"AI Tool Scraper total: {len(records)} unique products "
            f"(FP={len(fp_result) if isinstance(fp_result, list) else 0}, "
            f"TP={len(tp_result) if isinstance(tp_result, list) else 0}, "
            f"TopAI={len(topai_result) if isinstance(topai_result, list) else 0}, "
            f"TAAFT={len(taaft_records)})"
        )
        return records[:target_count]

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------
    @staticmethod
    def _deduplicate(records: list[dict]) -> list[dict]:
        seen: set[str] = set()
        unique: list[dict] = []
        for r in records:
            name = r.get("content", {}).get("productName", "").lower().strip()
            website = r.get("content", {}).get("website", "").lower().strip()
            key = name or website
            if key and key not in seen:
                seen.add(key)
                unique.append(r)
        return unique

    # ------------------------------------------------------------------
    # Record builder
    # ------------------------------------------------------------------
    @staticmethod
    def _make_record(
        source_name: str,
        source_url: str,
        name: str,
        description: Optional[str] = None,
        website: Optional[str] = None,
        pricing: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[dict]:
        if not name or len(name.strip()) < 2:
            return None
        return {
            "schemaVersion": "1.0",
            "recordType": "PRODUCT",
            "source": {"name": source_name, "url": source_url},
            "content": {
                "startupName": name.strip(),
                "productName": name.strip(),
                "pricingModel": pricing,
                "description": (description or "")[:500] or None,
                "website": website or source_url,
                "category": category or "AI Tool",
            },
            "collectedAt": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Pricing heuristic
    # ------------------------------------------------------------------
    @staticmethod
    def _infer_pricing(text: str) -> Optional[str]:
        lower = text.lower()
        if "free trial" in lower or ("free" in lower and ("paid" in lower or "premium" in lower)):
            return "FREEMIUM"
        if "freemium" in lower:
            return "FREEMIUM"
        if "free" in lower and "$" not in lower:
            return "FREE"
        if "enterprise" in lower:
            return "ENTERPRISE"
        if "$" in text or "/mo" in text or "paid" in lower:
            return "PAID"
        return None

    # ==================================================================
    #  FUTUREPEDIA  scraper
    # ==================================================================
    async def _scrape_futurepedia(self, target: int) -> list[dict]:
        """Scrape Futurepedia by iterating category pages.

        Each category page has 12 tool cards.  Categories have 1-5 pages.
        Selectors verified against live HTML:
          - Card container: div.flex.flex-col.bg-card....rounded-xl.border.shadow-lg
          - Tool link:      a[href*="/tool/"]
          - Tool name:      p.m-0.line-clamp-2  (or img alt)
          - Description:    p.text-muted-foreground.my-2.line-clamp-2
          - Tags:           a.hover\\:text-underline  (prefixed with #)
        """
        records: list[dict] = []
        source_name = "Futurepedia"
        max_pages_per_category = 12  # most have 1-5; safety margin for more coverage

        for cat_path in FUTUREPEDIA_CATEGORIES:
            if len(records) >= target:
                break

            cat_url = f"{FUTUREPEDIA_BASE}{cat_path}"
            category_label = cat_path.split("/")[-1].replace("-", " ").title()

            for page in range(1, max_pages_per_category + 1):
                if len(records) >= target:
                    break

                page_url = cat_url if page == 1 else f"{cat_url}?page={page}"
                soup = await self.fetch_and_parse(page_url)
                if not soup:
                    break

                cards = soup.select(
                    "div.flex.flex-col.bg-card.text-card-foreground"
                    ".h-full.w-full.rounded-xl.border.shadow-lg"
                )
                if not cards:
                    cards = soup.select("div.rounded-xl.border.shadow-lg")
                if not cards:
                    break  # empty page → category done

                new_count = 0
                for card in cards:
                    if len(records) >= target:
                        break
                    record = self._parse_futurepedia_card(
                        card, source_name, cat_url, category_label
                    )
                    if record:
                        records.append(record)
                        new_count += 1

                if new_count == 0:
                    break  # no new records → stop paginating

                await asyncio.sleep(0.6)

        self.logger.info(f"Futurepedia: {len(records)} products")
        return records

    def _parse_futurepedia_card(
        self, card, source_name: str, source_url: str, category: str
    ) -> Optional[dict]:
        """Parse a single Futurepedia tool card into a PRODUCT record."""
        # --- link ---
        link_el = card.select_one('a[href*="/tool/"]')
        if not link_el:
            return None
        href = link_el.get("href", "")
        if not href:
            return None
        tool_url = href if href.startswith("http") else f"{FUTUREPEDIA_BASE}{href}"

        # --- name ---
        name_el = card.select_one("p.m-0.line-clamp-2.overflow-hidden")
        if name_el:
            name = name_el.get_text(strip=True)
        else:
            img = card.select_one("img[alt]")
            name = img.get("alt", "").replace(" logo", "").strip() if img else ""
        if not name or len(name) < 2:
            return None

        # --- description ---
        desc_el = card.select_one("p.text-muted-foreground.my-2.line-clamp-2")
        description = desc_el.get_text(strip=True) if desc_el else None

        # --- pricing from card text ---
        card_text = card.get_text(strip=True)
        pricing = self._infer_pricing(card_text)

        # --- tags / sub-category ---
        tag_els = card.select("a")
        tags = []
        for t in tag_els:
            txt = t.get_text(strip=True)
            if txt.startswith("#"):
                tags.append(txt.lstrip("#"))
        sub_category = tags[0] if tags else category

        return self._make_record(
            source_name=source_name,
            source_url=tool_url,
            name=name,
            description=description,
            website=tool_url,
            pricing=pricing,
            category=sub_category,
        )

    # ==================================================================
    #  TOOLPILOT  scraper
    # ==================================================================
    async def _scrape_toolpilot(self, target: int) -> list[dict]:
        """Scrape ToolPilot by iterating Shopify collection pages.

        Each page has ~50 product-card elements.  Verified selectors:
          - Card container: <product-card class="product-card ...">
          - Title link:     a.product-card-title
          - Vendor:         div.product-card-vendor > a
          - Price:          span.price-item.price-item--regular
          - Label:          div.product-card--label  ("Free Trial", etc.)
        """
        records: list[dict] = []
        source_name = "ToolPilot"
        max_pages_per_collection = 5

        for coll_path in TOOLPILOT_COLLECTIONS:
            if len(records) >= target:
                break

            coll_url = f"{TOOLPILOT_BASE}{coll_path}"
            collection_label = coll_path.split("/")[-1].replace("-", " ").title()
            if collection_label == "All":
                collection_label = "AI Tool"

            for page in range(1, max_pages_per_collection + 1):
                if len(records) >= target:
                    break

                page_url = coll_url if page == 1 else f"{coll_url}?page={page}"
                soup = await self.fetch_and_parse(page_url)
                if not soup:
                    break

                cards = soup.select("product-card")
                if not cards:
                    break  # empty page

                new_count = 0
                for card in cards:
                    if len(records) >= target:
                        break
                    record = self._parse_toolpilot_card(
                        card, source_name, coll_url, collection_label
                    )
                    if record:
                        records.append(record)
                        new_count += 1

                if new_count == 0:
                    break

                await asyncio.sleep(0.6)

        self.logger.info(f"ToolPilot: {len(records)} products")
        return records

    def _parse_toolpilot_card(
        self, card, source_name: str, source_url: str, category: str
    ) -> Optional[dict]:
        """Parse a single ToolPilot <product-card> into a PRODUCT record."""
        # --- link ---
        link_el = card.select_one('a[href*="/products/"]')
        if not link_el:
            return None
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{TOOLPILOT_BASE}{href}"

        # --- name ---
        title_el = card.select_one("a.product-card-title")
        name = title_el.get_text(strip=True) if title_el else ""
        if not name or len(name) < 2:
            return None

        # --- vendor ---
        vendor_el = card.select_one("div.product-card-vendor a")
        vendor = vendor_el.get_text(strip=True) if vendor_el else ""

        # --- price ---
        price_el = card.select_one("span.price-item.price-item--regular")
        price_text = price_el.get_text(strip=True) if price_el else ""

        # --- label (Free Trial, etc.) ---
        label_el = card.select_one("div.product-card--label")
        label = label_el.get_text(strip=True) if label_el else ""

        # --- pricing model ---
        pricing = None
        combined = f"{price_text} {label}".lower()
        if price_text.strip().upper() == "FREE":
            pricing = "FREE"
        elif "free trial" in combined:
            pricing = "FREEMIUM"
        elif "$" in price_text:
            pricing = "PAID"

        return self._make_record(
            source_name=source_name,
            source_url=product_url,
            name=name,
            description=f"by {vendor}" if vendor else None,
            website=product_url,
            pricing=pricing,
            category=category,
        )

    # ==================================================================
    #  TopAI.tools  scraper
    # ==================================================================
    async def _scrape_topai(self, target: int) -> list[dict]:
        """Scrape TopAI.tools for AI tool listings.

        TopAI.tools is a directory of AI tools with server-rendered HTML.
        Each category page lists tools with name, description, and pricing.
        """
        records: list[dict] = []
        source_name = "TopAI.tools"

        categories = [
            "/category/productivity",
            "/category/marketing",
            "/category/coding",
            "/category/writing",
            "/category/image",
            "/category/video",
            "/category/audio",
            "/category/chat",
            "/category/design",
            "/category/education",
            "/category/seo",
            "/category/data",
            "/category/automation",
            "/category/sales",
            "/category/customer-support",
        ]

        for cat_path in categories:
            if len(records) >= target:
                break

            cat_url = f"https://topai.tools{cat_path}"
            category_label = cat_path.split("/")[-1].replace("-", " ").title()

            soup = await self.fetch_and_parse(cat_url)
            if not soup:
                continue

            # TopAI.tools uses card-based layout
            cards = soup.select(
                "div.tool-card, div.card, article, "
                "div[class*='tool'], div[class*='product']"
            )

            if not cards:
                # Try broader selectors
                cards = soup.select("a[href*='/tools/'], a[href*='/tool/']")

            for card in cards[:50]:
                if len(records) >= target:
                    break

                record = self._parse_topai_card(card, source_name, cat_url, category_label)
                if record:
                    records.append(record)

            await asyncio.sleep(0.5)

        self.logger.info(f"TopAI.tools: {len(records)} products")
        return records

    def _parse_topai_card(
        self, card, source_name: str, source_url: str, category: str
    ) -> Optional[dict]:
        """Parse a single TopAI.tools tool card into a PRODUCT record."""
        # Try to find a link
        link_el = card.select_one('a[href*="/tool"], a[href*="/tools/"]')
        if not link_el:
            # If card IS a link
            if card.name == "a":
                link_el = card
            else:
                link_el = card.select_one("a")

        if not link_el:
            return None

        href = link_el.get("href", "")
        if not href:
            return None
        tool_url = href if href.startswith("http") else f"https://topai.tools{href}"

        # Get name
        name = None
        for sel in ["h3", "h4", ".tool-name", ".card-title", "strong", "b"]:
            el = card.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                if name and len(name) >= 2:
                    break

        if not name:
            name = link_el.get_text(strip=True)

        if not name or len(name) < 2:
            return None

        # Get description
        desc_el = card.select_one("p, .description, .card-text, .tool-desc")
        description = desc_el.get_text(strip=True) if desc_el else None

        # Pricing heuristic
        card_text = card.get_text(strip=True)
        pricing = self._infer_pricing(card_text)

        return self._make_record(
            source_name=source_name,
            source_url=tool_url,
            name=name,
            description=description,
            website=tool_url,
            pricing=pricing,
            category=category,
        )

    # ==================================================================
    #  TAAFT  scraper  (cloudscraper in thread pool)
    # ==================================================================
    def _run_cloudscraper(self, url: str) -> Optional[str]:
        """Run cloudscraper synchronously (called via run_in_executor)."""
        try:
            import cloudscraper

            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
            resp = scraper.get(url, timeout=20)
            if resp.status_code == 200:
                return resp.text
        except Exception as e:
            self.logger.debug(f"Cloudscraper failed for {url}: {e}")
        return None

    async def _scrape_taaft(self) -> list[dict]:
        """Scrape TAAFT using cloudscraper.

        Strategy:
          1. Fetch the homepage — ~120 server-rendered tool rows with
             data-home-today-entity="ai" attributes containing name,
             description, category, price, and URL.
          2. Fetch a handful of /s/{topic}/ pages (~200 tools each)
             using div.li_row > div.ai_link_wrap selectors.
        """
        records: list[dict] = []
        source_name = "There's An AI For That"
        loop = asyncio.get_event_loop()

        # --- Step 1: homepage ---
        html = await loop.run_in_executor(
            None, self._run_cloudscraper, TAAFT_BASE
        )
        if html:
            soup = BeautifulSoup(html, "lxml")
            records.extend(self._parse_taaft_homepage(soup, source_name))

        # --- Step 2: topic pages for more breadth ---
        topics = [
            "chatbot", "image-generator", "writing", "coding",
            "productivity", "marketing", "seo", "music",
            "video", "education", "summarizer", "translation",
            "finance", "health", "design", "sales",
            "social-media", "email", "presentation", "automation",
            "data-analysis", "research", "customer-service", "hr",
            "ecommerce", "legal", "accounting", "real-estate",
        ]
        for topic in topics:
            if len(records) >= 400:
                break
            topic_url = f"{TAAFT_BASE}/s/{topic}/"
            html = await loop.run_in_executor(
                None, self._run_cloudscraper, topic_url
            )
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            records.extend(
                self._parse_taaft_topic_page(soup, source_name, topic)
            )
            await asyncio.sleep(1.5)

        self.logger.info(f"TAAFT: {len(records)} products")
        return records

    def _parse_taaft_homepage(
        self, soup: BeautifulSoup, source_name: str
    ) -> list[dict]:
        """Parse TAAFT homepage tool rows.

        Each row has:
          - data-home-today-entity="ai"  (filters tools vs news/models)
          - data-href                    (full tool URL)
          - .home-today-name-text        (tool name)
          - .tools-name-tagline          (description)
          - .task_label                  (category)
          - .tools-price-value           (price)
        """
        records: list[dict] = []
        rows = soup.select('div[data-home-today-entity="ai"]')

        for row in rows:
            href = row.get("data-href", "")
            if not href:
                continue
            tool_url = href.split("?")[0].rstrip("/")

            name_el = row.select_one(".home-today-name-text, .tools-name-text")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name or len(name) < 2:
                continue

            desc_el = row.select_one(".tools-name-tagline")
            description = desc_el.get_text(strip=True) if desc_el else None

            cat_el = row.select_one(".task_label.home-today-topic-link, a.task_label")
            category = cat_el.get_text(strip=True) if cat_el else "AI Tool"

            price_el = row.select_one(".tools-price-value")
            price_text = price_el.get_text(strip=True) if price_el else ""
            pricing = self._infer_pricing(price_text) if price_text else None

            records.append(
                self._make_record(
                    source_name=source_name,
                    source_url=tool_url,
                    name=name,
                    description=description,
                    website=tool_url,
                    pricing=pricing,
                    category=category,
                )
            )
        return records

    def _parse_taaft_topic_page(
        self, soup: BeautifulSoup, source_name: str, topic: str
    ) -> list[dict]:
        """Parse a TAAFT /s/{topic}/ page.

        Tools are inside div.li_row containers:
          - div.ai_link_wrap > a[href*="/ai/"]  (name + URL)
          - div.short_desc                      (description)
          - a.task_label                        (category)
        """
        records: list[dict] = []
        topic_label = topic.replace("-", " ").title()

        rows = soup.select("div.li_row")
        if not rows:
            # Fallback: parse ai_link_wrap divs directly
            wraps = soup.select("div.ai_link_wrap")
            for wrap in wraps:
                link = wrap.select_one('a[href*="/ai/"]')
                if not link:
                    continue
                href = link.get("href", "").split("?")[0].rstrip("/")
                name = link.get_text(strip=True)
                if not name or len(name) < 2:
                    continue
                parent = wrap.parent
                desc, cat = None, topic_label
                if parent:
                    desc_div = parent.select_one("div.short_desc")
                    if desc_div:
                        desc = desc_div.get_text(strip=True)
                    cat_el = parent.select_one("a.task_label")
                    if cat_el:
                        cat = cat_el.get_text(strip=True)
                records.append(
                    self._make_record(
                        source_name=source_name,
                        source_url=href,
                        name=name,
                        description=desc,
                        website=href,
                        pricing=None,
                        category=cat,
                    )
                )
            return records

        for row in rows:
            link = row.select_one('div.ai_link_wrap a[href*="/ai/"]')
            if not link:
                continue
            href = link.get("href", "").split("?")[0].rstrip("/")
            name = link.get_text(strip=True)
            if not name or len(name) < 2:
                continue

            desc_div = row.select_one("div.short_desc")
            description = desc_div.get_text(strip=True) if desc_div else None

            cat_el = row.select_one("a.task_label")
            category = cat_el.get_text(strip=True) if cat_el else topic_label

            records.append(
                self._make_record(
                    source_name=source_name,
                    source_url=href,
                    name=name,
                    description=description,
                    website=href,
                    pricing=None,
                    category=category,
                )
            )
        return records
