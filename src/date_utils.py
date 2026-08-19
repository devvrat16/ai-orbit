from datetime import datetime, timezone, timedelta
import re
from dateutil import parser

def parse_date(value: str | None, now=None) -> datetime | None:
    if not value: return None
    now = now or datetime.now(timezone.utc)
    s = value.strip().lower()
    m = re.match(r"(\d+)\s+(minute|minutes|min|hour|hours|day|days)\s+ago", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        seconds = n * (60 if unit.startswith("min") else 3600 if unit.startswith("hour") else 86400)
        return now - timedelta(seconds=seconds)
    if s in {"today", "just now"}: return now
    try:
        dt = parser.parse(value)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None

def is_fresh(dt: datetime | None, hours=24) -> bool:
    if not dt: return False
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return now - timedelta(hours=hours) <= dt <= now + timedelta(minutes=5)
