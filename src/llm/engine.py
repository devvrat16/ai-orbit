"""Multi-tier LLM extraction engine with fallback chain."""
import asyncio
import json
import logging
import re
import time
from typing import Optional
from src.llm.chunker import TextChunker
from src.llm.prompts import PROMPTS
from config import (
    LLM_FALLBACK_CHAIN, LLM_MAX_RETRIES_PER_TIER,
    LLM_REQUEST_TIMEOUT, LLM_CHUNK_MAX_TOKENS,
)

logger = logging.getLogger(__name__)


class LLMEngine:
    """Multi-tier LLM extraction with fallback chain, rate limit handling, and chunking."""

    def __init__(self):
        self.chunker = TextChunker(max_tokens=LLM_CHUNK_MAX_TOKENS)
        self._clients = {}
        self._stats = {"total": 0, "success": 0, "fallback": 0, "error": 0}
        self._rate_limits = {}  # provider -> next_available_time

    def _get_client(self, tier: dict):
        """Get or create LLM client for a tier."""
        provider = tier["provider"]
        model = tier["model"]
        api_key = tier["api_key"]

        if not api_key:
            return None

        cache_key = f"{provider}:{model}"
        if cache_key in self._clients:
            return self._clients[cache_key]

        try:
            if provider in ("gemini", "deepseek"):
                # OpenAI-compatible API
                import openai
                base_urls = {
                    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
                    "deepseek": "https://api.deepseek.com/v1",
                }
                client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_urls.get(provider, "https://api.openai.com/v1"),
                    timeout=LLM_REQUEST_TIMEOUT,
                )
                self._clients[cache_key] = (client, model)
                return (client, model)

            elif provider == "groq":
                import openai
                client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://api.groq.com/openai/v1",
                    timeout=LLM_REQUEST_TIMEOUT,
                )
                self._clients[cache_key] = (client, model)
                return (client, model)

        except Exception as e:
            logger.warning(f"Failed to create {provider} client: {e}")
            return None

        return None

    async def extract(self, text: str, entity_type: str) -> Optional[dict]:
        """Extract structured data from text using the LLM fallback chain."""
        if not text or len(text.strip()) < 20:
            return None

        prompt_template = PROMPTS.get(entity_type)
        if not prompt_template:
            logger.error(f"No prompt template for entity type: {entity_type}")
            return None

        self._stats["total"] += 1

        # Chunk the text
        chunks = self.chunker.chunk_for_extraction(text, entity_type)

        # Process chunks (for single-chunk content, this is straightforward)
        results = []
        for chunk_data in chunks:
            result = await self._extract_chunk(chunk_data["text"], prompt_template)
            if result:
                results.append(result)

        if not results:
            self._stats["error"] += 1
            return None

        # Merge results (for multi-chunk, take the first complete result)
        merged = results[0] if results else None

        # If multiple chunks, try to merge
        if len(results) > 1:
            merged = self._merge_results(results, entity_type)

        self._stats["success"] += 1
        return merged

    async def _extract_chunk(self, text: str, prompt_template: str) -> Optional[dict]:
        """Try extraction across the fallback chain."""
        prompt = prompt_template.format(content=text)

        for i, tier in enumerate(LLM_FALLBACK_CHAIN):
            client_info = self._get_client(tier)
            if not client_info:
                continue

            client, model = client_info
            provider = tier["provider"]

            # Check rate limit backoff
            if provider in self._rate_limits:
                wait_until = self._rate_limits[provider]
                if time.time() < wait_until:
                    continue

            for attempt in range(LLM_MAX_RETRIES_PER_TIER):
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "You are a precise data extraction assistant. Return only valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.1,
                        max_tokens=2000,
                    )

                    content = response.choices[0].message.content.strip()
                    return self._parse_json_response(content)

                except Exception as e:
                    error_str = str(e).lower()
                    logger.warning(f"[{provider}] Attempt {attempt+1} failed: {e}")

                    if "429" in error_str or "rate" in error_str or "too many" in error_str:
                        # Rate limited — exponential backoff
                        backoff = min(60, 2 ** (attempt + 2))  # 4s, 8s, 16s, 32s, 60s
                        self._rate_limits[provider] = time.time() + backoff
                        logger.info(f"[{provider}] Rate limited, backing off {backoff}s")
                        await asyncio.sleep(backoff)
                    elif "413" in error_str or "payload" in error_str or "context" in error_str:
                        # Context too large — skip this chunk
                        logger.warning(f"[{provider}] Payload too large, skipping chunk")
                        break
                    elif "401" in error_str or "403" in error_str or "auth" in error_str:
                        # Auth error — skip this provider
                        logger.warning(f"[{provider}] Auth error, skipping provider")
                        break
                    else:
                        # Generic error — retry with backoff
                        if attempt < LLM_MAX_RETRIES_PER_TIER - 1:
                            await asyncio.sleep(2 ** attempt)

            # Move to next tier in fallback chain
            if i < len(LLM_FALLBACK_CHAIN) - 1:
                self._stats["fallback"] += 1
                logger.info(f"Falling back from {provider} to next tier")

        return None

    def _parse_json_response(self, text: str) -> Optional[dict]:
        """Parse JSON from LLM response, handling common formatting issues."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding JSON object in text
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start != -1 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"Failed to parse JSON from LLM response: {text[:200]}...")
        return None

    def _merge_results(self, results: list[dict], entity_type: str) -> dict:
        """Merge results from multiple chunks, preferring non-null values."""
        if not results:
            return {}

        merged = results[0].copy()
        for result in results[1:]:
            for key, value in result.items():
                if value is not None and (merged.get(key) is None or merged.get(key) == ""):
                    merged[key] = value
                elif key in ("authors",) and isinstance(value, list) and isinstance(merged.get(key), list):
                    # Merge arrays
                    existing = set(merged[key])
                    for item in value:
                        if item not in existing:
                            merged[key].append(item)
                            existing.add(item)

        return merged

    @property
    def stats(self) -> dict:
        return self._stats.copy()
