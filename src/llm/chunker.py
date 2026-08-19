"""Intelligent text chunking to prevent 413 Payload Too Large errors."""
import re
from typing import Optional


class TextChunker:
    """Splits text into semantically dense chunks that fit within LLM context windows."""

    def __init__(self, max_tokens: int = 3000, overlap_tokens: int = 200):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        # Rough estimate: 1 token ≈ 4 characters
        self.max_chars = max_tokens * 4
        self.overlap_chars = overlap_tokens * 4

    def chunk_text(self, text: str) -> list[str]:
        """Split text into chunks, trying to break at paragraph/sentence boundaries."""
        if not text:
            return []

        # If text fits in one chunk, return as-is
        if len(text) <= self.max_chars:
            return [text]

        chunks = []
        remaining = text

        while remaining:
            if len(remaining) <= self.max_chars:
                chunks.append(remaining)
                break

            # Try to find a good break point
            break_point = self._find_break_point(remaining)

            chunk = remaining[:break_point].strip()
            if chunk:
                chunks.append(chunk)

            # Move forward with overlap
            start = max(0, break_point - self.overlap_chars)
            remaining = remaining[start:]

        return [c for c in chunks if c]

    def _find_break_point(self, text: str) -> int:
        """Find the best position to break text, preferring paragraph > sentence > word boundaries."""
        search_start = int(self.max_chars * 0.7)  # Start looking from 70% of max
        search_end = self.max_chars

        # Try paragraph break (double newline)
        last_paragraph = text.rfind("\n\n", search_start, search_end)
        if last_paragraph > search_start:
            return last_paragraph + 2

        # Try single newline
        last_newline = text.rfind("\n", search_start, search_end)
        if last_newline > search_start:
            return last_newline + 1

        # Try sentence break
        last_period = max(
            text.rfind(". ", search_start, search_end),
            text.rfind("! ", search_start, search_end),
            text.rfind("? ", search_start, search_end),
        )
        if last_period > search_start:
            return last_period + 2

        # Try comma or semicolon
        last_comma = max(
            text.rfind(", ", search_start, search_end),
            text.rfind("; ", search_start, search_end),
        )
        if last_comma > search_start:
            return last_comma + 2

        # Try word boundary (space)
        last_space = text.rfind(" ", search_start, search_end)
        if last_space > search_start:
            return last_space + 1

        # Hard cut at max_chars
        return self.max_chars

    def chunk_for_extraction(self, text: str, entity_type: str) -> list[dict]:
        """Chunk text with metadata for LLM extraction."""
        chunks = self.chunk_text(text)
        return [
            {
                "chunk_index": i,
                "total_chunks": len(chunks),
                "text": chunk,
                "entity_type": entity_type,
            }
            for i, chunk in enumerate(chunks)
        ]

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token count estimate."""
        return len(text) // 4
