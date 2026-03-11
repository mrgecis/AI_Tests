"""
Central configuration for Receipt Matcher.
All settings are loaded from environment variables (.env file).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = DATA_DIR / "chroma"

# Ensure required directories exist
for _d in (INPUT_DIR, OUTPUT_DIR, DATA_DIR, CHROMA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Google OAuth ───────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]

# One token file per Gmail account: token_<sanitised_email>.json
TOKEN_DIR = BASE_DIR / "data" / "tokens"
TOKEN_DIR.mkdir(parents=True, exist_ok=True)

# Gmail accounts to index (comma-separated in .env)
_raw_accounts = os.getenv("GMAIL_ACCOUNTS", "")
GMAIL_ACCOUNTS: list[str] = [a.strip() for a in _raw_accounts.split(",") if a.strip()]

# ── Anthropic ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-6"

# ── Matching thresholds ────────────────────────────────────────────────────────
AMOUNT_TOLERANCE_PCT: float = float(os.getenv("AMOUNT_TOLERANCE_PCT", "0.01"))
DATE_TOLERANCE_DAYS: int = int(os.getenv("DATE_TOLERANCE_DAYS", "3"))
MATCH_CONFIDENCE_THRESHOLD: float = float(os.getenv("MATCH_CONFIDENCE_THRESHOLD", "0.65"))

# Fuzzy-match threshold for merchant name (0-100, thefuzz score)
MERCHANT_FUZZY_THRESHOLD: int = 60

# ── ChromaDB ───────────────────────────────────────────────────────────────────
CHROMA_COLLECTION_NAME = "receipts_2025"

# ── Output CSV paths ──────────────────────────────────────────────────────────
MATCHED_CSV = BASE_DIR / "matched.csv"
REQUESTED_CSV = BASE_DIR / "requested.csv"
UNMATCHED_CSV = BASE_DIR / "unmatched.csv"

# ── Indexing scope ─────────────────────────────────────────────────────────────
INDEX_YEAR = 2025          # Which year's emails to index
MAX_EMAILS_PER_ACCOUNT = 5000   # Safety cap per Gmail account

# ── Orchestrator settings ──────────────────────────────────────────────────────
MAX_MATCH_ATTEMPTS = 3     # Give up after N attempts per transaction
