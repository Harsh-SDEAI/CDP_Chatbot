"""
scheduler.py  –  24-Hour Content Change Detector & Index Rebuilder

Reads BASE_URL from .env and path from DB. Every 24 hours, fetches the page,
compares content hash with stored hash, rebuilds index if changed.
"""

from __future__ import annotations

import os
import logging
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from scraping_file import check_and_rebuild_if_changed
from db import get_latest_indexed_path

log = logging.getLogger(__name__)


async def _check_url() -> None:
    base_url = os.getenv("BASE_URL")
    if not base_url:
        log.warning("Scheduler: BASE_URL not set in .env — skipping check.")
        return

    path = await asyncio.to_thread(get_latest_indexed_path)
    if not path:
        log.warning("Scheduler: No indexed path in DB — skipping check.")
        return

    full_url = base_url.rstrip("/") + "/" + path.lstrip("/")
    log.info("Scheduler: checking base_url=%s path=%s", base_url, path)

    try:
        openai_api_key = os.environ["OPENAI_API_KEY"]
        metadata, changed = await check_and_rebuild_if_changed(base_url, path, openai_api_key)
        if changed:
            log.info("Scheduler: index rebuilt for url=%s, chunk_count=%d", full_url, metadata["chunk_count"])
        else:
            log.info("Scheduler: no change for url=%s", full_url)
    except Exception as exc:
        log.warning("Scheduler: check/rebuild failed — keeping existing. Error: %s", exc)


async def _run_check() -> None:
    await _check_url()


_scheduler = AsyncIOScheduler()

def start_scheduler() -> None:
    _scheduler.add_job(
        _run_check, trigger="interval", hours=24,
        id="daily_content_check", replace_existing=True,
    )
    _scheduler.start()
    log.info("Scheduler: started — every 24 hours.")

def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler: stopped.")
