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
