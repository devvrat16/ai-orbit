"""Google Sheets output module — writes pipeline results to Google Sheets."""
import csv
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from src.storage import Storage
from config import OUTPUT_DIR, GSHEET_CREDENTIALS, GSHEET_ID

logger = logging.getLogger(__name__)


class OutputWriter:
    """Writes pipeline results to Google Sheets (if configured) or local CSV files."""

    TABS = {
        "Startups": "STARTUP",
        "Products": "PRODUCT",
        "Research Papers": "RESEARCH_PAPER",
        "Jobs": "JOB",
        "News": "NEWS",
    }

    def __init__(self, storage: Storage):
        self.storage = storage
        self.gspread_client = None
        self.spreadsheet = None

        # Try to initialize Google Sheets
        if GSHEET_CREDENTIALS and GSHEET_ID:
            self._init_gsheet()

    def _init_gsheet(self):
        """Initialize Google Sheets connection."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]

            creds = Credentials.from_service_account_file(
                GSHEET_CREDENTIALS, scopes=scopes
            )
            self.gspread_client = gspread.authorize(creds)
            self.spreadsheet = self.gspread_client.open_by_key(GSHEET_ID)
            logger.info("Google Sheets connected successfully")
        except Exception as e:
            logger.warning(f"Google Sheets not available: {e}. Using local CSV output.")
            self.gspread_client = None

    def write_all(self) -> dict[str, int]:
        """Write all tabs. Returns counts per tab."""
        counts = {}

        # Write each entity type
        for tab_name, record_type in self.TABS.items():
            records = self.storage.get_records(record_type)
            count = self._write_tab(tab_name, record_type, records)
            counts[tab_name] = count

        # Write entity mapping log
        mappings = self.storage.get_all_entity_mappings()
        count = self._write_entity_mappings(mappings)
        counts["Entity Mapping Log"] = count

        # Write local CSVs regardless
        self._write_local_csvs(counts)

        return counts

    def _write_tab(self, tab_name: str, record_type: str, records: list[dict]) -> int:
        """Write records to a Google Sheet tab."""
        if not records:
            logger.info(f"No records for {tab_name}, skipping")
            return 0

        if self.spreadsheet:
            return self._write_gsheet_tab(tab_name, record_type, records)
        else:
            return self._write_csv_tab(tab_name, records)

    def _write_gsheet_tab(self, tab_name: str, record_type: str, records: list[dict]) -> int:
        """Write to Google Sheets tab."""
        try:
            # Get or create worksheet
            try:
                worksheet = self.spreadsheet.worksheet(tab_name)
                worksheet.clear()
            except Exception:
                worksheet = self.spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=20)

            # Normalize records from storage format to envelope format
            normalized = [self._normalize_record(r) for r in records]

            # Build headers based on record type
            headers = self._get_headers(record_type)
            rows = [headers]

            for record in normalized:
                row = self._record_to_row(record, record_type)
                rows.append(row)

            # Update worksheet
            worksheet.update(range_name="A1", values=rows)

            # Format header row
            worksheet.format("A1:Z1", {
                "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            })

            logger.info(f"Wrote {len(records)} records to Google Sheets tab '{tab_name}'")
            return len(records)

        except Exception as e:
            logger.error(f"Failed to write to Google Sheets: {e}")
            return self._write_csv_tab(tab_name, records)

    def _write_csv_tab(self, tab_name: str, records: list[dict]) -> int:
        """Write to local CSV file."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filepath = OUTPUT_DIR / f"{tab_name.lower().replace(' ', '_')}.csv"

        if not records:
            return 0

        # Normalize records from storage format to envelope format
        normalized = [self._normalize_record(r) for r in records]

        # Get headers from first record type
        record_type = normalized[0].get("recordType", "") or normalized[0].get("record_type", "")
        headers = self._get_headers(record_type)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            for record in normalized:
                row = self._record_to_row(record, record_type)
                writer.writerow(row)

        logger.info(f"Wrote {len(records)} records to {filepath}")
        return len(records)

    def _normalize_record(self, record: dict) -> dict:
        """Normalize a record from storage format to envelope format."""
        # Already in envelope format?
        if "source" in record and isinstance(record["source"], dict):
            return record

        # Storage format: flat fields
        return {
            "recordType": record.get("record_type", ""),
            "source": {
                "name": record.get("source_name", ""),
                "url": record.get("source_url", ""),
            },
            "content": record.get("content", {}),
            "collectedAt": record.get("collected_at", ""),
        }

    def _write_entity_mappings(self, mappings: list[dict]) -> int:
        """Write entity mapping log."""
        if self.spreadsheet:
            try:
                try:
                    worksheet = self.spreadsheet.worksheet("Entity Mapping Log")
                    worksheet.clear()
                except Exception:
                    worksheet = self.spreadsheet.add_worksheet(title="Entity Mapping Log", rows=1000, cols=10)

                headers = ["Raw Name", "Canonical Name", "Confidence", "Source", "Record Type", "Mapped At"]
                rows = [headers]

                for m in mappings:
                    rows.append([
                        m.get("raw_name", ""),
                        m.get("canonical_name", ""),
                        f"{m.get('confidence', 0):.2f}",
                        m.get("source", ""),
                        m.get("record_type", ""),
                        datetime.utcnow().isoformat(),
                    ])

                worksheet.update(range_name="A1", values=rows)
                logger.info(f"Wrote {len(mappings)} entity mappings to Google Sheets")
                return len(mappings)

            except Exception as e:
                logger.error(f"Failed to write mappings to Google Sheets: {e}")

        # Fallback to CSV
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filepath = OUTPUT_DIR / "entity_mapping_log.csv"

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Raw Name", "Canonical Name", "Confidence", "Source", "Record Type", "Mapped At"])

            for m in mappings:
                writer.writerow([
                    m.get("raw_name", ""),
                    m.get("canonical_name", ""),
                    f"{m.get('confidence', 0):.2f}",
                    m.get("source", ""),
                    m.get("record_type", ""),
                    datetime.utcnow().isoformat(),
                ])

        logger.info(f"Wrote {len(mappings)} entity mappings to {filepath}")
        return len(mappings)

    def _get_headers(self, record_type: str) -> list[str]:
        """Get column headers for a record type."""
        headers_map = {
            "STARTUP": ["Record Type", "Entity Name", "Source Name", "Source URL",
                        "Description", "Employee Count", "Website", "Location",
                        "Industry", "Founded Year", "Collected At"],
            "PRODUCT": ["Record Type", "Product Name", "Startup Name", "Source Name",
                        "Source URL", "Pricing Model", "Description", "Website",
                        "Category", "Collected At"],
            "RESEARCH_PAPER": ["Record Type", "Title", "Authors", "Paper URL",
                               "GitHub URL", "GitHub Stars", "Published Date",
                               "Abstract", "Source Name", "Collected At"],
            "JOB": ["Record Type", "Company", "Title", "Source Name", "Source URL",
                    "Date", "Is Remote", "Role Family", "Location", "Job URL",
                    "Collected At"],
            "NEWS": ["Record Type", "Title", "Author", "Date", "Source Name",
                     "Source URL", "Summary", "Category", "Collected At"],
        }
        return headers_map.get(record_type, ["Data"])

    def _record_to_row(self, record: dict, record_type: str) -> list[str]:
        """Convert a record dict to a row list."""
        content = record.get("content", {})
        source = record.get("source", {})

        row_map = {
            "STARTUP": lambda: [
                "STARTUP",
                content.get("entityName", ""),
                source.get("name", ""),
                source.get("url", ""),
                content.get("description", "") or "",
                str(content.get("employeeCount", "")) if content.get("employeeCount") else "",
                content.get("website", "") or "",
                content.get("location", "") or "",
                content.get("industry", "") or "",
                str(content.get("founded_year", "")) if content.get("founded_year") else "",
                record.get("collectedAt", ""),
            ],
            "PRODUCT": lambda: [
                "PRODUCT",
                content.get("productName", "") or content.get("startupName", ""),
                content.get("startupName", ""),
                source.get("name", ""),
                source.get("url", ""),
                content.get("pricingModel", "") or "",
                content.get("description", "") or "",
                content.get("website", "") or "",
                content.get("category", "") or "",
                record.get("collectedAt", ""),
            ],
            "RESEARCH_PAPER": lambda: [
                "RESEARCH_PAPER",
                content.get("title", ""),
                ", ".join(content.get("authors", [])),
                content.get("paper_url", ""),
                content.get("github_url", "") or "",
                str(content.get("github_stars", "")) if content.get("github_stars") is not None else "",
                content.get("published_date", "") or "",
                (content.get("abstract", "") or "")[:500],
                source.get("name", ""),
                record.get("collectedAt", ""),
            ],
            "JOB": lambda: [
                "JOB",
                content.get("company", ""),
                content.get("title", "") or "",
                source.get("name", ""),
                source.get("url", ""),
                content.get("date", "") or "",
                str(content.get("is_remote", False)),
                content.get("role_family", "") or "",
                content.get("location", "") or "",
                content.get("url", "") or "",
                record.get("collectedAt", ""),
            ],
            "NEWS": lambda: [
                "NEWS",
                content.get("title", ""),
                content.get("author", "") or "",
                content.get("date", "") or "",
                source.get("name", ""),
                source.get("url", ""),
                content.get("summary", "") or "",
                content.get("category", "") or "",
                record.get("collectedAt", ""),
            ],
        }

        row_fn = row_map.get(record_type)
        return row_fn() if row_fn else [""]

    def _write_local_csvs(self, counts: dict):
        """Ensure all data is also saved locally as CSV."""
        for tab_name, count in counts.items():
            if count > 0:
                logger.info(f"  {tab_name}: {count} records")
