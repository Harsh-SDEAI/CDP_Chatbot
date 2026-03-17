"""
Shared configuration, constants, and database helpers.
"""
from pathlib import Path
import re
import psycopg2

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = "postgresql://postgres:admin123@localhost:5432/CDP_ASSISTANT"

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = ""  # paste your OpenAI key here

# ── Paths ─────────────────────────────────────────────────────────────────────
STORAGE_DIR = Path("storage")
STORAGE_DIR.mkdir(exist_ok=True)

TEXT_FOLDER = str(STORAGE_DIR)
SAVE_PATH = str(STORAGE_DIR)

IMAGES_DIR = STORAGE_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)

FAISS_DIR = STORAGE_DIR / "faiss"
FAISS_DIR.mkdir(exist_ok=True)

# ── KB Export ─────────────────────────────────────────────────────────────────
MAX_FILE_SIZE = 25 * 1024  # 25 KB
BASE_FILE_NAME = "KB_update"

# ── Admin FAISS Config ────────────────────────────────────────────────────────
FAISS_INDEX_PATH = FAISS_DIR / "index.faiss"
FAISS_META_PATH = FAISS_DIR / "index_meta.json"
EMBEDDING_DIM = 1536  # text-embedding-3-small


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


def clean_text(text):
    text = re.sub(r'<[^>]*>', '', text or '')
    text = re.sub(r'[\n\r\t]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    return text.strip()
