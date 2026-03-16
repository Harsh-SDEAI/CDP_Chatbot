"""
Shared configuration, constants, and database helpers.
"""
from dotenv import load_dotenv
from pathlib import Path
import os
import re
import pyodbc

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DB_SERVER = os.getenv("DB_SERVER", "")
DB_DRIVER = os.getenv("DB_DRIVER", "")
DB_NAME = os.getenv("DB_NAME", "")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ── Paths ─────────────────────────────────────────────────────────────────────
TEXT_FOLDER = os.getenv("TEXT_FOLDER", r"D:\cdpgpt_enhancement\data")
SAVE_PATH = os.getenv("SAVE_PATH", r"D:\cdpgpt_enhancement\data")

STORAGE_DIR = Path("storage")
STORAGE_DIR.mkdir(exist_ok=True)

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
    return pyodbc.connect(
        f"DRIVER={DB_DRIVER};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};PWD={DB_PASSWORD};"
    )


def clean_text(text):
    text = re.sub(r'<[^>]*>', '', text or '')
    text = re.sub(r'[\n\r\t]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    return text.strip()
