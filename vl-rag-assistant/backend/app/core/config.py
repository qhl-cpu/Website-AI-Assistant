import os
from pathlib import Path

from dotenv import load_dotenv


# backend/app/core/config.py
# Parents:
# config.py -> core -> app -> backend -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Load .env from project root first, then backend/.env if needed.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"

PRODUCTION_ORIGINS = [
    "https://www.vancouverlaser.com",
    "https://vancouverlaser.com",
]

DEVELOPMENT_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    *PRODUCTION_ORIGINS,
]

configured_origins = os.getenv("ALLOWED_ORIGINS")

if configured_origins:
    ALLOWED_ORIGINS = [
        origin.strip().rstrip("/")
        for origin in configured_origins.split(",")
        if origin.strip()
    ]
else:
    ALLOWED_ORIGINS = (
        PRODUCTION_ORIGINS
        if IS_PRODUCTION
        else DEVELOPMENT_ORIGINS
    )

ENABLE_DIAGNOSTIC_ENDPOINTS = os.getenv(
    "ENABLE_DIAGNOSTIC_ENDPOINTS",
    "false" if IS_PRODUCTION else "true",
).strip().lower() in {"1", "true", "yes", "on"}

CHAT_RATE_LIMIT_ENABLED = os.getenv(
    "CHAT_RATE_LIMIT_ENABLED",
    "true",
).strip().lower() in {"1", "true", "yes", "on"}

# Generous public-chat defaults. These can be tuned without changing code.
CHAT_VISITOR_BURST_REQUESTS = int(
    os.getenv("CHAT_VISITOR_BURST_REQUESTS", "5")
)
CHAT_VISITOR_BURST_WINDOW_SECONDS = int(
    os.getenv("CHAT_VISITOR_BURST_WINDOW_SECONDS", "30")
)
CHAT_VISITOR_SUSTAINED_REQUESTS = int(
    os.getenv("CHAT_VISITOR_SUSTAINED_REQUESTS", "20")
)
CHAT_VISITOR_SUSTAINED_WINDOW_SECONDS = int(
    os.getenv("CHAT_VISITOR_SUSTAINED_WINDOW_SECONDS", "600")
)
CHAT_VISITOR_DAILY_REQUESTS = int(
    os.getenv("CHAT_VISITOR_DAILY_REQUESTS", "100")
)
CHAT_VISITOR_DAILY_WINDOW_SECONDS = int(
    os.getenv("CHAT_VISITOR_DAILY_WINDOW_SECONDS", "86400")
)
CHAT_IP_SUSTAINED_REQUESTS = int(
    os.getenv("CHAT_IP_SUSTAINED_REQUESTS", "300")
)
CHAT_IP_SUSTAINED_WINDOW_SECONDS = int(
    os.getenv("CHAT_IP_SUSTAINED_WINDOW_SECONDS", "600")
)
CHAT_IP_DAILY_REQUESTS = int(
    os.getenv("CHAT_IP_DAILY_REQUESTS", "2000")
)
CHAT_IP_DAILY_WINDOW_SECONDS = int(
    os.getenv("CHAT_IP_DAILY_WINDOW_SECONDS", "86400")
)
TRUST_X_FORWARDED_FOR = os.getenv(
    "TRUST_X_FORWARDED_FOR",
    "true" if IS_PRODUCTION else "false",
).strip().lower() in {"1", "true", "yes", "on"}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

TOP_K = int(os.getenv("TOP_K", "8"))
MAX_CONTEXT_CHARS_PER_CHUNK = int(os.getenv("MAX_CONTEXT_CHARS_PER_CHUNK", "1200"))

if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY. Add it to your .env file.")

if not QDRANT_URL:
    raise ValueError("Missing QDRANT_URL. Add it to your .env file.")

if not QDRANT_API_KEY:
    raise ValueError("Missing QDRANT_API_KEY. Add it to your .env file.")

if not QDRANT_COLLECTION_NAME:
    raise ValueError("Missing QDRANT_COLLECTION_NAME. Add it to your .env file.")
