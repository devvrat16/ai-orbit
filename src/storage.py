"""SQLite storage with WAL mode and idempotent, insert-only ingestion.

The pipeline never overwrites an existing source URL during normal incremental runs.
Use refresh_metrics.py explicitly when a dynamic field such as GitHub stars must be
updated.
"""
import json, sqlite3, logging
from datetime import datetime, timezone
from pathlib import Path
from config import DB_PATH

log = logging.getLogger(__name__)

class Storage:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_type TEXT NOT NULL,
            source_name TEXT,
            source_url TEXT NOT NULL UNIQUE,
            content_json TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_records_type ON records(record_type);
        CREATE INDEX IF NOT EXISTS idx_records_collected ON records(collected_at);

        CREATE TABLE IF NOT EXISTS entity_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_name TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            confidence REAL,
            source TEXT,
            record_type TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_mappings_raw ON entity_mappings(raw_name);

        CREATE TABLE IF NOT EXISTS crawl_state (
            source_url TEXT PRIMARY KEY,
            last_crawled TEXT,
            status TEXT,
            record_count INTEGER DEFAULT 0
        );
        """)
        self.conn.commit()

    def insert_if_new(self, record_type, source_name, source_url, content, collected_at):
        if not source_url:
            return False
        cur = self.conn.execute(
            "SELECT 1 FROM records WHERE source_url=? LIMIT 1", (source_url,)
        )
        if cur.fetchone():
            return False
        self.conn.execute(
            "INSERT INTO records(record_type,source_name,source_url,content_json,collected_at) VALUES(?,?,?,?,?)",
            (record_type, source_name, source_url, json.dumps(content, ensure_ascii=False), collected_at)
        )
        self.conn.commit()
        return True

    def upsert_record(self, record_type, source_name, source_url, content, collected_at, update_existing=False):
        """Compatibility API. Normal runs are insert-only; explicit refresh can update."""
        if not update_existing:
            return self.insert_if_new(record_type, source_name, source_url, content, collected_at)
        self.conn.execute("""
            INSERT INTO records(record_type,source_name,source_url,content_json,collected_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(source_url) DO UPDATE SET
              record_type=excluded.record_type,
              source_name=excluded.source_name,
              content_json=excluded.content_json,
              collected_at=excluded.collected_at
        """,(record_type,source_name,source_url,json.dumps(content,ensure_ascii=False),collected_at))
        self.conn.commit()
        return True

    def is_url_collected(self, source_url):
        return self.conn.execute("SELECT 1 FROM records WHERE source_url=?", (source_url,)).fetchone() is not None

    def get_records(self, record_type, limit=100000):
        rows=self.conn.execute(
            "SELECT * FROM records WHERE record_type=? ORDER BY collected_at DESC LIMIT ?",
            (record_type,limit)
        ).fetchall()
        return [{
            "id":r["id"],"record_type":r["record_type"],"source_name":r["source_name"],
            "source_url":r["source_url"],"content":json.loads(r["content_json"]),
            "collected_at":r["collected_at"]
        } for r in rows]

    def get_record_count(self, record_type):
        return self.conn.execute("SELECT COUNT(*) FROM records WHERE record_type=?", (record_type,)).fetchone()[0]

    def get_all_entity_mappings(self):
        rows=self.conn.execute("SELECT raw_name,canonical_name,confidence,source,record_type,created_at FROM entity_mappings ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def upsert_entity_mapping(self, raw_name, canonical_name, confidence, source, record_type):
        self.conn.execute("""
            INSERT INTO entity_mappings(raw_name,canonical_name,confidence,source,record_type)
            SELECT ?,?,?,?,? WHERE NOT EXISTS(
                SELECT 1 FROM entity_mappings WHERE raw_name=? AND canonical_name=? AND source=? AND record_type=?
            )
        """,(raw_name,canonical_name,confidence,source,record_type,
             raw_name,canonical_name,source,record_type))
        self.conn.commit()

    def update_crawl_state(self, source_url, status, record_count=0):
        self.conn.execute("""
        INSERT INTO crawl_state(source_url,last_crawled,status,record_count)
        VALUES(?,?,?,?)
        ON CONFLICT(source_url) DO UPDATE SET last_crawled=excluded.last_crawled,status=excluded.status,record_count=excluded.record_count
        """,(source_url,datetime.now(timezone.utc).isoformat(),status,record_count))
        self.conn.commit()

    def counts(self):
        rows=self.conn.execute("SELECT record_type,COUNT(*) n FROM records GROUP BY record_type").fetchall()
        return {r["record_type"]:r["n"] for r in rows}

    def close(self):
        self.conn.close()
