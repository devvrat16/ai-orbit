# Six-source integration guide

This package is an upgrade to the previous AI Orbit / AI Signal project. You do **not** need to throw away your existing data.

## Recommended: use this ZIP as the new project

1. Back up your existing project.
2. Extract this package.
3. Copy your real `.env` into the new project.
4. If your existing `data/` is newer, copy that `data/` into the new project.
5. Install dependencies.
6. Run the incremental pipeline.

Commands:

```bash
cd ~/Downloads
unzip ai_orbit_pipeline_six_sources.zip
cd ai_orbit_signal_combined
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then put your own credentials in `.env`.

Run all source families:

```bash
python main.py
```

The run performs:

```text
GitHub API ───────────────┐
Hugging Face API ─────────┤
YouTube Data API ─────────┤
News/RSS ─────────────────┤
Official product sites ───┼→ Normalize → Deduplicate → Resolve → Graph → Export
AI directories ───────────┘
```

## If you want to integrate into the old project instead

Copy these files/directories:

```text
src/sources/github_source.py
src/sources/huggingface_source.py
src/sources/youtube_source.py
src/sources/official_site.py
src/sources/__init__.py
main.py
config.py
export_catalog.py
.env.example
```

Do not delete your existing `data/` or SQLite database.

## Required environment variables

```env
GITHUB_TOKEN=
YOUTUBE_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
DEEPSEEK_API_KEY=
```

Hugging Face's public endpoints can work without a token for basic discovery. GitHub and YouTube benefit from their respective API keys.

## Run only one source family

Existing focused commands remain available for the original collectors:

```bash
python main.py --startups-only
python main.py --products-only
python main.py --papers-only
python main.py --news-only
python main.py --jobs-only
```

For the six new API-first adapters, the safest mode is the normal incremental run:

```bash
python main.py
```

A source with no key or a temporary failure is skipped and reported in the final `sources` section rather than terminating the entire run.

## Verify that all six were invoked

At the end of a run, inspect:

```text
sources.github
sources.hugging_face
sources.youtube
sources.news_rss
sources.official_product_sites
sources.ai_directories
```

The `added` and `sqlite_counts` sections show exactly what entered the dataset.

## Deployment

The root `index.html` is a static public explorer. It reads `data/*.json` and does not require API keys. Deploy the repository root to Vercel. Never put `.env` in GitHub or in frontend code.
