"""
scheduler.py  –  Hourly Content Change Detector & Index Rebuilder
"""

from __future__ import annotations

import os
import re
import hashlib
import logging
import asyncio
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from scraping_file import (
    build_index,
    load_index,
    _make_cache_key,
    _html_to_markdown,
    _parse_qa_blocks,
)

log = logging.getLogger(__name__)

# ── Storage dirs ──────────────────────────────────────────────────────────────
STORAGE_DIR    = os.getenv("STORAGE_DIR", ".storage")
CACHE_DIR      = os.path.join(STORAGE_DIR, "faiss_cache")
MD_STORAGE_DIR = os.path.join(STORAGE_DIR, "md_storage")
HASH_DIR       = os.path.join(STORAGE_DIR, "hash_store")
for _d in (CACHE_DIR, MD_STORAGE_DIR, HASH_DIR):
    os.makedirs(_d, exist_ok=True)

_watched: dict[str, tuple[str, str, str]] = {}


def register_session(session_id: str, url: str, metric: str) -> None:
    key = _make_cache_key(session_id, url, metric)
    _watched[key] = (session_id, url, metric)
    log.info("Scheduler: registered session=%s url=%s metric=%s", session_id, url, metric)


def _hash_path(key: str) -> str:
    return os.path.join(HASH_DIR, f"{key}.hash")

def _md_path(key: str) -> str:
    return os.path.join(MD_STORAGE_DIR, f"{key}.md")

def _load_stored_hash(key: str) -> str | None:
    path = _hash_path(key)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return f.read().strip()

def _save_hash(key: str, content_hash: str) -> None:
    with open(_hash_path(key), "w") as f:
        f.write(content_hash)

def _save_md(key: str, markdown_text: str, url: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(_md_path(key), "w", encoding="utf-8") as f:
        f.write(f"# Scraped Content\n\n")
        f.write(f"**Source URL:** {url}  \n")
        f.write(f"**Scraped At:** {now}  \n\n")
        f.write("---\n\n")
        f.write(markdown_text)
    log.info("Scheduler: saved MD → %s", _md_path(key))


def _fetch_and_convert(url: str) -> tuple[str, str, str]:
    """Fetch URL → (markdown_text, plain_text, sha256_hash)

    Uses the same two-pass strategy as _scrape_url in scraping_file.py:
      Pass 1 — _html_to_markdown: renders page structure (headings, lists,
               paragraphs) but SKIPS Q&A blocks since they are JS-rendered.
      Pass 2 — _parse_qa_blocks: parses Q&A pairs from raw plain text,
               which always contains the collapsed Q./A. content regardless
               of whether JavaScript has run.
    """
    with httpx.Client(follow_redirects=True, timeout=20) as client:
        r = client.get(url, headers={"User-Agent": "Mozilla/5.0 (RAG-Scheduler/1.0)"})
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    structure_md = _html_to_markdown(soup)

    plain_text = soup.get_text(separator=" ", strip=True)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()

    qa_md = _parse_qa_blocks(plain_text)

    if qa_md:
        markdown_text = structure_md + "\n\n---\n\n## Questions & Answers\n\n" + qa_md
    else:
        markdown_text = structure_md

    content_hash = hashlib.sha256(plain_text.encode()).hexdigest()
    return markdown_text, plain_text, content_hash


async def _check_one(key: str, session_id: str, url: str, metric: str) -> None:
    log.info("Scheduler: checking session=%s url=%s", session_id, url)

    try:
        markdown_text, plain_text, new_hash = await asyncio.to_thread(_fetch_and_convert, url)
    except Exception as exc:
        log.warning("Scheduler: fetch failed session=%s — keeping existing. Error: %s", session_id, exc)
        return

    old_hash = await asyncio.to_thread(_load_stored_hash, key)
    if old_hash == new_hash:
        log.info("Scheduler: no change for session=%s", session_id)
        return

    log.info("Scheduler: content changed session=%s — rebuilding", session_id)

    try:
        await asyncio.to_thread(_save_md, key, markdown_text, url)
    except Exception as exc:
        log.warning("Scheduler: MD save failed session=%s. Error: %s", session_id, exc)
        return

    try:
        openai_api_key = os.environ["OPENAI_API_KEY"]
        await build_index(
            session_id=session_id, url=url,
            similarity_metric=metric, cache_dir=CACHE_DIR,
            openai_api_key=openai_api_key,
        )
        await asyncio.to_thread(_save_hash, key, new_hash)
        log.info("Scheduler: storage updated session=%s", session_id)
    except Exception as exc:
        log.warning("Scheduler: rebuild failed session=%s. Error: %s", session_id, exc)


async def _run_all_checks() -> None:
    if not _watched:
        log.info("Scheduler: no sessions registered.")
        return
    log.info("Scheduler: checking %d session(s).", len(_watched))
    tasks = [
        _check_one(key, sid, url, metric)
        for key, (sid, url, metric) in list(_watched.items())
    ]
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("Scheduler: check complete.")


_scheduler = AsyncIOScheduler()

def start_scheduler() -> None:
    _scheduler.add_job(
        _run_all_checks, trigger="interval", hours=1,
        id="hourly_content_check", replace_existing=True,
    )
    _scheduler.start()
    log.info("Scheduler: started — every 1 hour.")

def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler: stopped.")