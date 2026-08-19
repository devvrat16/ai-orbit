# AI Signal — Technical Architecture

## 1. System architecture

```text
                         SOURCE LAYER
     ┌────────┬────────┬────────┬─────────┬────────────┐
     │ GitHub │ HF     │ ArXiv  │ RSS     │ Directories│
     │ YC     │ YouTube│ PWC    │ Jobs    │ Official   │
     └────┬───┴────┬───┴────┬───┴────┬────┴──────┬─────┘
          └─────────────── DISCOVERY ────────────────┘
                              │
                         Async HTTP
                    retry / jitter / limits
                              │
                         EXTRACTION
                              │
                    HTML / XML / JSON / RSS
                              │
                     CLEAN + NORMALIZE
                              │
                 URL canonicalization / dates
                              │
                      DEDUPLICATION
                    stable URL + stable UUID
                              │
                 ┌────────────┴────────────┐
                 │                         │
          deterministic resolver       optional LLM
                 │                  Gemini → Groq → DeepSeek
                 └────────────┬────────────┘
                              │
                     RELATIONSHIP MAPPING
                              │
                     VALIDATION / EVIDENCE
                              │
                ┌─────────────┴─────────────┐
                │                           │
           SQLite / JSON               AI Signal UI
        canonical source of truth      search / graph
```

## 2. Storage strategy

SQLite with WAL mode is used for the trial because it provides:

- zero operational setup
- transactional writes
- concurrent reads
- source URL uniqueness
- deterministic incremental ingestion

The schema stores raw source metadata and normalized content. Canonical JSON is exported for the public frontend.

At 500k+ records, PostgreSQL becomes the primary transactional store. Raw HTML/RSS belongs in object storage, and graph traversal can move to Neo4j/Neptune. Vector storage is supplementary and never replaces the canonical identity store.

## 3. Incremental contract

The ingestion key is the normalized source URL.

Normal run:

```text
discover source item
      ↓
source URL already known?
   yes ─────→ skip persistence/reprocessing
   no
      ↓
extract → normalize → resolve → validate → persist
```

The state is durable in SQLite and `state/`. This makes reruns idempotent.

Dynamic metrics such as GitHub stars are deliberately separated from normal ingestion and can be refreshed by a dedicated job.

## 4. Entity resolution

The resolver uses:

- Unicode normalization
- punctuation/suffix cleanup
- canonical aliases
- RapidFuzz token similarity
- confidence thresholds
- mapping audit records

A mapping is never silently discarded. The raw string, canonical result, confidence, source and record type are retained.

## 5. Relationship graph

Relationships are created only when evidence exists:

- `DEVELOPS`
- `SOLVES`
- `INTEGRATES_WITH`
- `MAINTAINS`
- `HAS_REPOSITORY`
- `RUNS`

Every edge carries:

```json
{
  "source_id": "...",
  "relation": "DEVELOPS",
  "target_id": "...",
  "evidence_url": "...",
  "confidence": 0.99,
  "metadata": {"reason": "..."}
}
```

This makes graph edges auditable.

## 6. LLM orchestration

LLMs are used as an extraction/enrichment layer, not as a data source.

The chain is:

```text
Gemini Flash
   ↓ failure / 429 / 413
Groq
   ↓ failure
DeepSeek
```

Payloads are chunked before requests. 429 responses use exponential backoff and jitter. 413/context errors reduce or skip the offending chunk and continue through the fallback chain.

No model response is allowed to create a record without an originating source URL.

## 7. Freshness

News/jobs use source publication timestamps. Relative dates are normalized to UTC. If no trustworthy date exists, the source is marked unusable for the strict 24-hour feed rather than being treated as fresh.

Distributed deployment should use a shared idempotency key:

```text
hash(normalized_source_url)
```

with a database uniqueness constraint.

## 8. Anti-bot and JS rendering

The preferred hierarchy is:

1. API
2. RSS/Atom
3. server-rendered HTML
4. permitted browser rendering
5. graceful skip

403/CAPTCHA responses are not brute-forced. Domain rate limits and exponential backoff protect both the pipeline and source systems.

## 9. Public application

The frontend is static and reads canonical JSON.

This avoids exposing:

- GitHub tokens
- LLM API keys
- database credentials

The UI provides:

- global search
- type/source/category filters
- relationship filters
- entity detail
- connected entities
- evidence URLs
- GitHub metrics

The same JSON dataset can be consumed by a future React/Next.js frontend without changing the ingestion engine.
