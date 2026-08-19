# Final Trial Submission Checklist

## Dataset
- [x] 250–300 representative entities
- [x] 265 unique entities
- [x] Tools
- [x] Tasks
- [x] Companies
- [x] News
- [x] Videos
- [x] Robots
- [x] Devices
- [x] Models
- [x] Repositories
- [x] MCP
- [x] Collections
- [x] Personal AI
- [x] Creative
- [x] Recently Added view

## Engineering
- [x] API-first source adapters
- [x] Incremental insertion by source URL
- [x] Stable UUIDs
- [x] URL normalization
- [x] HTML/RSS sanitization
- [x] Entity resolution with RapidFuzz + aliases
- [x] Deterministic relationships
- [x] Evidence URL + confidence
- [x] Graceful network/rate-limit handling
- [x] Explicit submission validator

## Six source families
- [x] GitHub
- [x] Hugging Face
- [x] YouTube
- [x] News/RSS
- [x] Official product/company enrichment
- [x] AI directories

## Deliverables
- [x] `src/`
- [x] `data/`
- [x] `run.py`
- [x] `README.md`
- [x] `relationships.json`
- [x] `entity_mapping_log.json`
- [x] `.env.example`
- [x] Static public dashboard
- [x] Google-Sheets-ready workbook

## Before sending

```bash
python validate_submission.py
git status
git add .
git status
```

Make sure no secret files are staged.
