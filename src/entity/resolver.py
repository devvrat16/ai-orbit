"""Entity resolution engine — canonicalizes messy entity names."""
import re
import logging
from typing import Optional
from rapidfuzz import fuzz, process
from src.entity.seed import CANONICAL_ENTITIES
from src.storage import Storage
from config import FUZZY_MATCH_THRESHOLD

logger = logging.getLogger(__name__)


class EntityResolver:
    """Canonicalizes entity names using fuzzy matching against a seed list."""

    def __init__(self, storage: Storage):
        self.storage = storage
        # Build lookup structures
        self._canonical_map: dict[str, str] = {}  # alias -> canonical
        self._canonical_list: list[str] = list(CANONICAL_ENTITIES.keys())

        # Build reverse lookup
        for canonical, aliases in CANONICAL_ENTITIES.items():
            for alias in aliases:
                self._canonical_map[alias.lower().strip()] = canonical

        logger.info(f"Entity resolver initialized with {len(self._canonical_list)} canonical entities")

    def resolve(self, raw_name: str, source: str = "", record_type: str = "") -> str:
        """Resolve a raw entity name to its canonical form.

        Returns the canonical name if confidence >= threshold, otherwise returns
        the cleaned raw name.
        """
        if not raw_name or not raw_name.strip():
            return raw_name

        cleaned = self._clean_name(raw_name)

        # Exact match in canonical map
        if cleaned.lower() in self._canonical_map:
            canonical = self._canonical_map[cleaned.lower()]
            self.storage.upsert_entity_mapping(raw_name, canonical, 1.0, source, record_type)
            return canonical

        # Check if raw name IS a canonical name
        if cleaned.lower() in [c.lower() for c in self._canonical_list]:
            canonical = next(c for c in self._canonical_list if c.lower() == cleaned.lower())
            self.storage.upsert_entity_mapping(raw_name, canonical, 1.0, source, record_type)
            return canonical

        # Fuzzy match against all canonical names
        best_match = self._fuzzy_match(cleaned)
        if best_match:
            canonical, score = best_match
            if score >= FUZZY_MATCH_THRESHOLD:
                self.storage.upsert_entity_mapping(raw_name, canonical, score / 100.0, source, record_type)
                logger.debug(f"Fuzzy match: '{raw_name}' -> '{canonical}' (score: {score})")
                return canonical

        # Fuzzy match against aliases
        best_alias_match = self._fuzzy_match_alias(cleaned)
        if best_alias_match:
            canonical, score = best_alias_match
            if score >= FUZZY_MATCH_THRESHOLD:
                self.storage.upsert_entity_mapping(raw_name, canonical, score / 100.0, source, record_type)
                logger.debug(f"Alias match: '{raw_name}' -> '{canonical}' (score: {score})")
                return canonical

        # No match found — return cleaned name
        self.storage.upsert_entity_mapping(raw_name, cleaned, 0.0, source, record_type)
        return cleaned

    def _clean_name(self, name: str) -> str:
        """Clean and normalize entity name."""
        if not name:
            return name

        # Remove common suffixes (order matters — more specific first)
        suffixes = [
            r',?\s*inc\.?$', r',?\s*llc\.?$', r',?\s*corp\.?$',
            r',?\s*ltd\.?$', r',?\s*co\.?$', r',?\s*company$',
            r',?\s*technologies$', r',?\s*systems$',
            r'\s*&\s*',
        ]

        cleaned = name.strip()
        for suffix in suffixes:
            cleaned = re.sub(suffix, '', cleaned, flags=re.IGNORECASE)

        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Remove leading/trailing punctuation
        cleaned = cleaned.strip('.,;:!?-')

        return cleaned if cleaned else name.strip()

    def _fuzzy_match(self, name: str) -> Optional[tuple[str, float]]:
        """Fuzzy match against canonical names."""
        if not name:
            return None

        # Use token sort ratio for order-independent matching
        result = process.extractOne(
            name.lower(),
            [c.lower() for c in self._canonical_list],
            scorer=fuzz.token_sort_ratio,
            score_cutoff=FUZZY_MATCH_THRESHOLD - 5,  # slightly lower threshold for initial filter
        )

        if result:
            match_str, score, idx = result
            canonical = self._canonical_list[idx]
            return (canonical, score)

        return None

    def _fuzzy_match_alias(self, name: str) -> Optional[tuple[str, float]]:
        """Fuzzy match against known aliases."""
        if not name:
            return None

        aliases = list(self._canonical_map.keys())
        canonical_for_alias = list(self._canonical_map.values())

        result = process.extractOne(
            name.lower(),
            aliases,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=FUZZY_MATCH_THRESHOLD - 5,
        )

        if result:
            match_str, score, idx = result
            canonical = canonical_for_alias[idx]
            return (canonical, score)

        return None

    def resolve_batch(self, names: list[str], source: str = "", record_type: str = "") -> dict[str, str]:
        """Resolve a batch of names. Returns mapping of raw -> canonical."""
        return {name: self.resolve(name, source, record_type) for name in names}

    def get_stats(self) -> dict:
        """Get resolver statistics."""
        mappings = self.storage.get_all_entity_mappings()
        total = len(mappings)
        resolved = sum(1 for m in mappings if m["confidence"] > 0)
        return {
            "total_mappings": total,
            "resolved": resolved,
            "unresolved": total - resolved,
            "resolution_rate": f"{(resolved/total*100):.1f}%" if total > 0 else "0%",
        }
