# AI Orbit — AI Ecosystem Ingestion Pipeline

> **Production-oriented, API-first data ingestion pipeline for discovering, normalizing, deduplicating, classifying, validating, and relationship-mapping entities across the global AI ecosystem.**

AI Orbit combines a modular Python ingestion engine with an interactive web dashboard for exploring the resulting AI ecosystem graph.

The project is designed around the assessment workflow:

**Discovery → Extraction → Cleaning → Normalization → Deduplication → Classification → Relationship Mapping → Validation**

---

## 1. Project Overview

The goal of this project is to build a reliable ingestion system rather than a simple scraper.

The pipeline collects representative AI ecosystem data from multiple source types, converts heterogeneous records into a common entity schema, resolves duplicate entities, enriches domain-specific metadata, extracts relationships, validates the resulting dataset, and exports JSON suitable for downstream applications.

### Main objectives

- API-first discovery wherever structured APIs are available
- Multi-source ingestion
- Common schema normalization
- Deterministic entity resolution
- URL normalization
- HTML/RSS sanitization
- Domain-specific metadata enrichment
- Relationship extraction
- Validation and quality reporting
- Incremental/resilient collection
- JSON export for the AI Orbit frontend
- Interactive ecosystem exploration

---

# 2. Architecture

```text
                         ┌─────────────────────┐
                         │   Source Discovery  │
                         └──────────┬──────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
       GitHub                 Hugging Face              YouTube
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    │
                         ┌──────────▼──────────┐
                         │     Extraction      │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │      Cleaning       │
                         │ HTML / RSS / Text   │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │    Normalization    │
                         │ Names / URLs / Data │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │  Entity Resolution  │
                         │   + Deduplication   │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │   Classification    │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │ Relationship Mapper │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │      Validation     │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │ JSON / Dashboard    │
                         └─────────────────────┘
```

---

# 3. Multi-Source Strategy

The pipeline is designed to use the six source families specified by the assessment.

| Source | Purpose |
|---|---|
| GitHub | Repositories, open-source projects, MCP-related projects, stars, languages |
| Hugging Face | AI/ML models and datasets |
| YouTube | Technical videos, demos, tutorials and reviews |
| News / RSS | AI announcements, research and ecosystem updates |
| Official Product Sites | Product/company metadata and enrichment |
| AI Directories | Tool discovery and cross-reference candidates |

The implementation intentionally prefers structured APIs before HTML scraping.

When an API is unavailable or insufficient, the corresponding source can fall back to a resilient HTTP/HTML extraction path.

---

# 4. Entity Coverage

The common catalog supports the assessment categories:

```text
tools
tasks
companies
news
videos
robots
devices
models
repositories
mcp
collections
personal
creative
new / recently added
```

The architecture also allows additional entity types to be introduced without changing the core ingestion flow.

---

# 5. Common Entity Schema

Every normalized entity follows the common structure:

```json
{
  "id": "stable-generated-uuid",
  "entity_type": "tool",
  "name": "Example AI",
  "description": "AI-powered example product.",
  "url": "https://example.com",
  "categories": [
    "generative-ai"
  ],
  "source": {
    "name": "Official Product Site",
    "url": "https://example.com"
  }
}
```

### Required fields

- `id`
- `entity_type`
- `name`
- `description`
- `url`
- `categories`
- `source`

IDs are generated deterministically/stably so that the same logical entity can be recognized across ingestion runs.

---

# 6. Specialized Metadata

Domain-specific entities can contain additional metadata.

## Models

Examples:

```json
{
  "license": "Apache-2.0",
  "modalities": ["text", "image"],
  "provider": "Example Provider"
}
```

## Repositories

Examples:

```json
{
  "stars": 12345,
  "primary_language": "Python",
  "last_updated": "2026-08-19T00:00:00Z"
}
```

## MCP Servers

Examples:

```json
{
  "installation_methods": [
    "npm",
    "docker"
  ],
  "runtime_requirements": [
    "Node.js 20+"
  ]
}
```

## Companies

Examples:

```json
{
  "founding_year": 2020,
  "industry_sector": "Artificial Intelligence",
  "headquarters": "United States"
}
```

---

# 7. Relationship Mapping

The pipeline generates `relationships.json`.

Relationships represent the connections between ecosystem entities.

Supported relationship examples include:

```text
Company ──DEVELOPS──────> Tool
Company ──DEVELOPS──────> Model

Tool ─────SOLVES────────> Task

MCP ──────INTEGRATES_WITH> Tool

Device ───RUNS──────────> Model

Repository ─HAS_REPOSITORY> Entity
```

Example:

```json
{
  "source_id": "company-123",
  "target_id": "tool-456",
  "relationship": "DEVELOPS",
  "confidence": 0.92,
  "source": "official_product_site"
}
```

The relationship layer is intentionally separate from entity storage so that the ecosystem can be represented as a graph.

---

# 8. Entity Resolution

Entity resolution is a core part of the pipeline.

For example:

```text
OpenAI
Open AI
openai
OPENAI
```

should resolve to the same canonical entity where the evidence supports that conclusion.

The resolver can use:

- normalized names
- punctuation removal
- whitespace normalization
- lowercase comparison
- aliases/seeds
- normalized URLs
- domain matching
- source identifiers
- deterministic similarity signals

The goal is to avoid creating multiple records for the same company, tool, model or repository.

---

# 9. URL Normalization

URLs are normalized before comparison and storage.

Typical normalization includes:

- protocol normalization
- hostname normalization
- trailing slash handling
- tracking parameter removal where appropriate
- canonical path handling
- redirect-aware resolution when supported

This helps detect records such as:

```text
https://example.com
https://www.example.com/
https://example.com/?utm_source=test
```

as the same underlying resource when appropriate.

---

# 10. Cleaning and Sanitization

Source data can contain:

- HTML tags
- RSS markup
- duplicated whitespace
- tracking URLs
- navigation text
- malformed descriptions
- incomplete metadata

The cleaning stage converts source-specific content into normalized text and structured fields.

This prevents raw HTML/RSS fragments from leaking into the final catalog.

---

# 11. Resilience and Error Handling

The ingestion engine is designed to continue operating when individual sources fail.

Examples:

```text
API timeout
HTTP 403
HTTP 429 rate limit
missing API key
malformed XML
invalid HTML
missing metadata
blocked directory
unavailable GitHub repository
```

Expected behavior:

```text
Source failure
     ↓
log warning/error
     ↓
retry when appropriate
     ↓
apply backoff
     ↓
continue other sources
     ↓
produce partial but valid output
```

A single failing source should not invalidate the complete ingestion run.

---

# 12. Rate Limiting

External APIs have different limits.

The pipeline therefore uses:

- request throttling
- concurrency controls
- retry handling
- exponential/backoff delays where appropriate
- fast-fail behavior for non-retryable responses
- source-specific limits

For example, HTTP `403` responses are not blindly retried forever, while rate-limit responses such as `429` can trigger controlled backoff.

---

# 13. Hugging Face Integration

Hugging Face is used as a dedicated discovery source for:

- AI/ML models
- datasets
- provider metadata
- model URLs
- dataset URLs

The integration supports public Hugging Face discovery without requiring paid inference.

A Hugging Face token can optionally be supplied for authenticated API access and higher/private-resource capabilities.

Environment variable:

```env
HF_TOKEN=
```

The token must never be committed to Git.

---

# 14. GitHub Integration

GitHub is used for:

- repository discovery
- repository metadata
- stars
- primary language
- update timestamps
- MCP/open-source project discovery
- repository-to-entity relationships

Optional environment variable:

```env
GITHUB_TOKEN=
```

Using a token helps avoid anonymous API limits.

---

# 15. YouTube Integration

YouTube is used to discover:

- AI tutorials
- technical demonstrations
- product reviews
- research explainers
- AI ecosystem videos

Optional environment variable:

```env
YOUTUBE_API_KEY=
```

The resulting records are normalized into the common catalog schema.

---

# 16. News / RSS

News ingestion supports RSS feeds for:

- AI announcements
- research updates
- product launches
- company news
- ecosystem developments

RSS records are cleaned and normalized before entering the catalog.

The pipeline can attach freshness metadata so recent records can be identified separately.

---

# 17. Official Product Sites

Official product sites are primarily used for enrichment and verification.

Examples of information that can be enriched:

- product description
- official URL
- company
- product capabilities
- pricing information when available
- supported categories
- official documentation links

Official sources are preferred over secondary descriptions when both are available.

---

# 18. AI Directories

AI directories are useful for discovering candidate tools and cross-referencing metadata.

They are treated as discovery sources rather than unquestioned ground truth.

Directory records can be:

```text
discovered
   ↓
normalized
   ↓
cross-referenced
   ↓
deduplicated
   ↓
validated
   ↓
accepted/rejected
```

This prevents low-quality directory data from automatically becoming canonical data.

---

# 19. Incremental Ingestion

The pipeline supports incremental operation.

Instead of rebuilding everything from zero every time:

```text
Existing catalog
       +
New source candidates
       ↓
Entity resolution
       ↓
Only new/changed entities
       ↓
Updated catalog
```

This reduces unnecessary requests and makes recurring ingestion practical.

---

# 20. Data Quality

The assessment prioritizes quality over raw volume.

Quality checks include:

- required field validation
- valid entity types
- URL validation
- duplicate detection
- relationship endpoint validation
- missing metadata checks
- source attribution
- normalized names
- normalized URLs
- malformed records
- relationship consistency

The validation stage should produce a machine-readable report.

---

# 21. Expected Dataset Size

The assessment target is approximately:

```text
250–300 representative final entities
```

The pipeline may collect substantially more candidates internally.

For example:

```text
Source candidates
       ↓
Thousands of raw candidates
       ↓
Cleaning
       ↓
Normalization
       ↓
Deduplication
       ↓
Classification
       ↓
Representative final catalog
       ↓
250–300+ high-quality entities
```

This distinction is important: **candidate volume is not the same as final catalog size.**

---

# 22. Output Files

The pipeline produces structured JSON outputs under `data/`.

Typical outputs include:

```text
data/
├── catalog.json
├── relationships.json
├── validation_report.json
├── source_coverage.json
└── ...
```

### `catalog.json`

Canonical entity catalog.

### `relationships.json`

Graph edges connecting entities.

### `validation_report.json`

Data-quality and schema validation results.

### `source_coverage.json`

Source-level collection and freshness information.

---

# 23. Repository Structure

```text
ai-orbit-ingestion-pipeline/
│
├── src/
│   ├── entity/
│   │   ├── resolver.py
│   │   └── seed.py
│   │
│   ├── scrapers/
│   │   ├── base.py
│   │   ├── paper_scraper.py
│   │   ├── news_scraper.py
│   │   └── ...
│   │
│   ├── sources/
│   │   ├── github_source.py
│   │   ├── huggingface_source.py
│   │   ├── youtube_source.py
│   │   ├── official_site.py
│   │   └── ...
│   │
│   ├── schemas.py
│   ├── relationships.py
│   ├── storage.py
│   ├── http_client.py
│   └── url_utils.py
│
├── data/
│   ├── catalog.json
│   ├── relationships.json
│   └── validation_report.json
│
├── index.html
├── run.py
├── main.py
├── config.py
├── build_relationships.py
├── export_catalog.py
├── validate_submission.py
├── requirements.txt
├── vercel.json
├── architecture.md
├── architecture.pdf
├── .env.example
├── .gitignore
└── README.md
```

---

# 24. Environment Variables

Create a local `.env` file:

```env
GITHUB_TOKEN=
YOUTUBE_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
DEEPSEEK_API_KEY=
HF_TOKEN=

OFFICIAL_ENRICH_LIMIT=30
YOUTUBE_PER_QUERY=15
HF_MODEL_LIMIT=250
HF_DATASET_LIMIT=100
GITHUB_PER_QUERY=50
```

### Security

Never commit:

```text
.env
```

Commit only:

```text
.env.example
```

The `.gitignore` should contain:

```gitignore
.env
.env.*
!.env.example
.venv/
__pycache__/
.DS_Store
.vercel/
```

---

# 25. Local Setup

## Clone

```bash
git clone https://github.com/<YOUR_USERNAME>/ai-orbit-ingestion-pipeline.git
cd ai-orbit-ingestion-pipeline
```

## Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Install dependencies

```bash
pip install -r requirements.txt
```

## Configure environment

```bash
cp .env.example .env
```

Edit:

```bash
nano .env
```

Add the API keys that you actually have.

---

# 26. Run the Pipeline

Depending on the selected entry point:

```bash
python run.py
```

or:

```bash
python main.py
```

For development/debugging, individual source modules can also be executed where supported.

---

# 27. Validate

Run:

```bash
python validate_submission.py
```

A successful validation should report zero schema/validation errors.

Also verify:

```bash
python -m compileall src
```

---

# 28. Build Relationships

If relationship generation is a separate pipeline stage:

```bash
python build_relationships.py
```

Then verify:

```text
data/relationships.json
```

contains valid source and target entity IDs.

---

# 29. Frontend Dashboard

The project includes an interactive AI ecosystem dashboard.

The dashboard is designed around:

- AI ecosystem discovery
- entity search
- category filtering
- source filtering
- relationship inspection
- validation status
- pipeline statistics
- dataset exploration

The visual system uses a dark graphite/grey interface with restrained accent colors so the data remains the primary focus.

---

# 30. Run Frontend Locally

For the static dashboard:

```bash
python3 -m http.server 8000
```

Open:

```text
http://localhost:8000
```

The frontend reads the generated JSON data and presents the ecosystem through the dashboard.

---

# 31. Deployment

## GitHub

Initialize:

```bash
git init
git branch -M main
```

Add the remote:

```bash
git remote add origin https://github.com/<YOUR_USERNAME>/ai-orbit-ingestion-pipeline.git
```

Commit:

```bash
git add .
git commit -m "Initial AI Orbit ingestion pipeline"
```

Push:

```bash
git push -u origin main
```

---

## Vercel

The static dashboard can be deployed through Vercel.

Recommended configuration:

```text
Framework:
Other

Root Directory:
.

Build Command:
empty

Output Directory:
.

Install Command:
empty
```

The root `index.html` is the frontend entry point.

### Important

Vercel serves the frontend. It should not be treated as the long-running Python ingestion worker.

A production architecture can therefore be:

```text
                GitHub
                   │
       ┌───────────┴───────────┐
       │                       │
 Python ingestion          Frontend
       │                       │
 APIs → JSON data           Vercel
       │                       │
       └───────────┬───────────┘
                   │
             AI Orbit UI
```

For scheduled ingestion, run the Python pipeline on an appropriate worker/cron environment and publish the resulting JSON to the frontend data location.

---

# 32. API-First Design

The project follows an API-first philosophy.

Preferred order:

```text
Structured API
     ↓
Official feed
     ↓
Official page
     ↓
Directory page
     ↓
HTML fallback
```

Brute-force scraping is intentionally avoided where structured information is available.

Benefits:

- cleaner metadata
- easier parsing
- fewer layout dependencies
- better reproducibility
- easier error handling
- lower maintenance cost

---

# 33. Failure Handling

The pipeline follows graceful degradation.

Example:

```text
Hugging Face unavailable
        ↓
log warning
        ↓
continue GitHub
        ↓
continue YouTube
        ↓
continue RSS
        ↓
continue official sites
        ↓
produce partial valid catalog
```

This is preferable to terminating the entire ingestion run because one external provider failed.

---

# 34. Logging

Logging records:

- source start/end
- candidate counts
- successful records
- failed requests
- retry attempts
- rate limiting
- deduplication counts
- relationship counts
- validation results

This makes ingestion runs auditable and easier to debug.

---

# 35. Assessment Requirements Checklist

| Requirement | Status |
|---|---|
| Modular Python pipeline | Implemented |
| Discovery stage | Implemented |
| Extraction stage | Implemented |
| Cleaning/sanitization | Implemented |
| Normalization | Implemented |
| Entity resolution | Implemented |
| Deduplication | Implemented |
| Classification | Implemented |
| Relationship mapping | Implemented |
| Validation | Implemented |
| GitHub source | Implemented |
| Hugging Face source | Implemented |
| YouTube source | Implemented |
| News/RSS source | Implemented |
| Official product source | Implemented |
| AI directory source | Implemented |
| Common entity schema | Implemented |
| Model metadata | Supported |
| Repository metadata | Supported |
| MCP metadata | Supported |
| Company metadata | Supported |
| `relationships.json` | Implemented |
| Resilient HTTP handling | Implemented |
| Logging | Implemented |
| JSON outputs | Implemented |
| `src/` architecture | Implemented |
| `data/` outputs | Implemented |
| `run.py` | Included |
| `README.md` | Included |
| Interactive dashboard | Included |
| GitHub deployment | Supported |
| Vercel frontend deployment | Supported |

---

# 36. Engineering Decisions

### Why API-first?

APIs provide structured fields and predictable contracts, reducing fragile HTML parsing.

### Why deterministic entity resolution?

AI companies and products appear under many name variations. Deterministic canonicalization makes repeated ingestion stable and explainable.

### Why separate relationships from entities?

The entity catalog and graph edges evolve independently. Keeping relationships separate makes the dataset easier to validate and consume.

### Why preserve source attribution?

Every entity should be traceable to the source from which it was discovered or verified.

### Why incremental ingestion?

A production ingestion system should update existing knowledge rather than repeatedly rebuilding the entire catalog.

---

# 37. Quality Gates

Before submission, verify:

```bash
python -m compileall src
python validate_submission.py
```

Then confirm:

```text
✓ No API secrets committed
✓ Required JSON files exist
✓ Entity IDs are stable
✓ Entity URLs are normalized
✓ Duplicate entities are resolved
✓ Relationship endpoints exist
✓ Source attribution exists
✓ Validation errors are understood
✓ README documents architecture
✓ Frontend loads generated data
✓ GitHub repository is clean
```

---

# 38. Security

Do not commit API keys.

If a secret was accidentally pushed to GitHub:

1. Revoke/rotate the key immediately.
2. Remove it from the working tree.
3. Remove it from Git history if necessary.
4. Add `.env` to `.gitignore`.
5. Create a new secret.
6. Store secrets in Vercel/project environment variables only when required.

---

# 39. Current Project Snapshot

The dashboard/pipeline can expose metrics such as:

```text
Total Entities
Ecosystem Relationships
Validation Errors
Duplicates Merged
Data Sources
Categories
```

These values should be generated from the current output data rather than hard-coded so the dashboard remains synchronized with each ingestion run.

---

# 40. Evaluation Alignment

The implementation is intentionally aligned with the assessment weighting.

### Data Quality — 25%

- schema validation
- cleaning
- normalization
- source attribution
- deduplication
- metadata enrichment

### Architecture — 20%

- modular source adapters
- reusable HTTP layer
- entity resolver
- validation layer
- separate relationship layer
- structured output layer

### Discovery — 15%

- GitHub
- Hugging Face
- YouTube
- RSS
- official sites
- AI directories

### Entity Resolution — 15%

- canonical names
- aliases
- normalized URLs
- deterministic matching
- duplicate merging

### Relationships — 10%

- DEVELOP(S)
- SOLVES
- INTEGRATES_WITH
- RUNS
- repository relationships

### Error Handling — 10%

- retries
- backoff
- timeouts
- rate-limit handling
- graceful degradation
- logging

### Documentation — 5%

- architecture
- setup
- environment
- source strategy
- validation
- deployment

---

# 41. Final Submission

The final repository should contain:

```text
AI Orbit Ingestion Pipeline
│
├── Source adapters
├── Normalization
├── Entity resolution
├── Deduplication
├── Classification
├── Relationship extraction
├── Validation
├── JSON data
├── Interactive dashboard
├── Documentation
└── Deployment configuration
```

The key engineering principle is:

> **Collect broadly, normalize consistently, resolve deterministically, validate aggressively, and preserve relationships and provenance.**

---

## License

This project is intended as an engineering assessment/demo project.

Third-party data remains subject to the licenses and terms of the original providers.
