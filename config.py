"""Unified configuration for the AI Orbit / AI Signal pipeline."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "pipeline.db"
OUTPUT_DIR = DATA_DIR / "output"
STATE_DIR = BASE_DIR / "state"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
HF_TOKEN = os.getenv("HF_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

LLM_CHUNK_MAX_TOKENS = int(os.getenv("LLM_CHUNK_MAX_TOKENS", "3000"))
LLM_REQUEST_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "60"))
LLM_MAX_RETRIES_PER_TIER = int(os.getenv("LLM_MAX_RETRIES_PER_TIER", "2"))
LLM_FALLBACK_CHAIN = [
    {"provider":"gemini","model":os.getenv("LLM_MODEL_GEMINI","gemini-2.5-flash"),"api_key":GEMINI_API_KEY},
    {"provider":"groq","model":os.getenv("LLM_MODEL_GROQ","llama-3.3-70b-versatile"),"api_key":GROQ_API_KEY},
    {"provider":"deepseek","model":os.getenv("LLM_MODEL_DEEPSEEK","deepseek-chat"),"api_key":DEEPSEEK_API_KEY},
]

SCRAPE_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY","15"))
SCRAPE_RATE_LIMIT_PER_DOMAIN = float(os.getenv("SCRAPE_RATE_LIMIT_PER_DOMAIN","1.5"))
SCRAPE_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT_SECONDS","30"))
SCRAPE_MAX_RETRIES = int(os.getenv("SCRAPE_MAX_RETRIES","3"))
SCRAPE_BACKOFF_BASE = float(os.getenv("SCRAPE_BACKOFF_BASE","2"))
SCRAPE_BACKOFF_MAX = int(os.getenv("SCRAPE_BACKOFF_MAX","60"))
SCRAPE_JITTER_MAX = float(os.getenv("SCRAPE_JITTER_MAX","2"))

TARGET_STARTUPS = int(os.getenv("TARGET_STARTUPS","30"))
TARGET_PRODUCTS = int(os.getenv("TARGET_PRODUCTS","30"))
TARGET_PAPERS = int(os.getenv("TARGET_PAPERS","30"))
OFFICIAL_ENRICH_LIMIT = int(os.getenv("OFFICIAL_ENRICH_LIMIT","30"))
YOUTUBE_PER_QUERY = int(os.getenv("YOUTUBE_PER_QUERY","3"))
HF_MODEL_LIMIT = int(os.getenv("HF_MODEL_LIMIT","35"))
HF_DATASET_LIMIT = int(os.getenv("HF_DATASET_LIMIT","5"))
GITHUB_PER_QUERY = int(os.getenv("GITHUB_PER_QUERY","8"))

FRESHNESS_HOURS = int(os.getenv("FRESHNESS_HOURS","24"))
FUZZY_MATCH_THRESHOLD = int(os.getenv("FUZZY_MATCH_THRESHOLD","88"))

GSHEET_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS","")
GSHEET_ID = os.getenv("GOOGLE_SHEET_ID","")

SOURCE_USER_AGENT = os.getenv(
    "SOURCE_USER_AGENT",
    "AI-Signal-Research/1.0 (+https://github.com/)"
)
