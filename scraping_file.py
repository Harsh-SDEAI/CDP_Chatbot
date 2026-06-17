"""
scraping_file.py — Scrape URL → Markdown → FAISS index (subfolder per path+datetime)
"""

from __future__ import annotations

import os, re, json, hashlib, asyncio, glob
from datetime import datetime, timezone
from typing import Optional

import httpx, faiss, numpy as np
from bs4 import BeautifulSoup, NavigableString
from openai import AsyncOpenAI

from db import save_content_hash, get_latest_content_hash, get_latest_indexed_path

# ── Config ────────────────────────────────────────────────────────────────────
EMBED_MODEL   = "text-embedding-3-small"
EMBED_DIM     = 1536
CHUNK_SIZE    = 300
CHUNK_OVERLAP = 50
STORAGE_DIR   = os.getenv("STORAGE_DIR", ".storage")

os.makedirs(STORAGE_DIR, exist_ok=True)

# Headings that mark where the FAQ/accordion zone begins — stop structure scrape here
FAQ_HEADINGS = {"hear it from the concierge", "hear it from", "faqs", "faq",
                "questions & answers", "questions and answers", "contact", "quick links"}

# CSS class/id fragments that identify accordion containers — skip entirely
FAQ_CLASSES  = {"accordion", "faq", "qa-", "q-a", "expand", "collapse", "panel"}

# Category labels used inside Q&A plain text
QA_CATEGORIES = sorted([
    "Plan Your Visit", "Accommodations", "Campgrounds", "Food/Dining",
    "Shops", "Attractions", "Antiques", "Art", "Crafts", "Services",
    "Surrounding Area", "Ticket Booth",
], key=len, reverse=True)

# Plain-text markers where Q&A parsing should stop (footer/nav bleed)
QA_STOP_MARKERS = ["CONTACT", "QUICK LINKS", "Follow Us", "Download App",
                   "Register Now", "© 20", "Privacy Policy", "Site Map"]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _make_index_key(url: str) -> str:
    """Index key is derived from the URL only — one index per URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:24]


def _content_hash(text: str) -> str:
    """SHA-256 hash of the scraped content — used to detect page changes."""
    return hashlib.sha256(text.encode()).hexdigest()


def _datetime_stamp() -> str:
    """Return current UTC datetime as YYYYMMDD_HHMMSS."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _short_name(path: str) -> str:
    """Extract short name from path for subfolder naming.

    /FamilyGuide/CooperstownConcierge → concierge
    /FamilyGuide/abc                  → abc
    /FamilyGuide/Dining               → dining
    """
    last_part = path.rstrip("/").rsplit("/", 1)[-1]
    return last_part.lower()


def _chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_SIZE].strip())
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if c]


async def _embed(client: AsyncOpenAI, texts: list[str]) -> np.ndarray:
    resp = await client.embeddings.create(model=EMBED_MODEL, input=texts)
    vecs = np.array([d.embedding for d in resp.data], dtype=np.float32)
    vecs /= np.where((n := np.linalg.norm(vecs, axis=1, keepdims=True)) == 0, 1, n)
    return vecs


# ── HTML → Markdown (intro/structure only, stops at FAQ boundary) ─────────────
def _html_to_markdown(soup: BeautifulSoup) -> str:
    HMAP = {"h1": "#", "h2": "##", "h3": "###", "h4": "####", "h5": "#####", "h6": "######"}
    lines: list[str] = []
    stopped = [False]

    def txt(el) -> str:
        return re.sub(r"\s+", " ", el.get_text(separator=" ", strip=True))

    def is_faq_el(el) -> bool:
        combined = " ".join(el.get("class", [])).lower() + " " + (el.get("id") or "").lower()
        return any(f in combined for f in FAQ_CLASSES)

    def walk(el) -> None:
        if stopped[0] or isinstance(el, NavigableString) or not el.name:
            return
        tag = el.name

        if tag in HMAP:
            t = txt(el)
            if t.lower().strip() in FAQ_HEADINGS:
                stopped[0] = True
                return
            lines.append(f"\n{HMAP[tag]} {t}\n")

        elif tag == "p":
            for img in el.find_all("img", recursive=True):
                if src := img.get("src", "").strip():
                    lines.append(f"\n![{(img.get('alt') or img.get('title') or '').strip()}]({src})\n")
            if t := txt(el):
                lines.append(f"\n{t}\n")

        elif tag in ("ul", "ol"):
            lines.append("")
            for i, li in enumerate(el.find_all("li", recursive=False), 1):
                if t := txt(li):
                    lines.append(f"{'%d.' % i if tag == 'ol' else '-'} {t}")
            lines.append("")

        elif tag == "dl":
            for child in el.find_all(["dt", "dd"], recursive=False):
                if t := txt(child):
                    lines.append(f"\n**{'Q' if child.name == 'dt' else 'A'}. {t}**\n")

        elif tag == "img":
            if src := el.get("src", "").strip():
                lines.append(f"\n![{(el.get('alt') or el.get('title') or '').strip()}]({src})\n")

        elif tag in ("div", "section", "article", "main"):
            if not is_faq_el(el):
                for child in el.children:
                    walk(child)

        elif tag not in ("span", "a", "em", "i", "strong", "b", "label", "input", "button", "svg", "br"):
            for child in el.children:
                walk(child)

    for child in (soup.find("body") or soup).children:
        walk(child)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# ── Plain text → Q&A Markdown ─────────────────────────────────────────────────
def _parse_qa(plain_text: str) -> str:
    first_q = re.search(r'(?<!\w)Q\. ', plain_text)
    if not first_q:
        return ""

    qa_text = plain_text[max(0, first_q.start() - 30):]
    for marker in QA_STOP_MARKERS:
        if (pos := qa_text.find(marker)) != -1:
            qa_text = qa_text[:pos]

    def strip_cat(text: str, from_end=False):
        t = text.strip()
        for label in QA_CATEGORIES:
            if from_end:
                if t.endswith(label):
                    return t[:-len(label)].strip(), label
                if m := re.search(rf'[.!?]\s+({re.escape(label)})$', t):
                    return t[:m.start() + 1].strip(), label
            elif t.startswith(label):
                return label, t[len(label):].strip()
        return (None, t) if not from_end else (t, None)

    out: list[str] = []
    cur_cat: str | None = None

    for block in re.split(r'(?<!\w)(?=Q\. )', qa_text):
        block = block.strip()
        if not block:
            continue

        cat, block = strip_cat(block)
        if cat and cat != cur_cat:
            out.append(f"\n### {cat}\n")
            cur_cat = cat

        if not block.startswith("Q. "):
            continue

        parts = re.split(r'(?<!\w)(?=A\. )', block, maxsplit=1)
        q = re.sub(r'^Q\.\s*', '', re.sub(r'\s+', ' ', parts[0])).strip()
        a = re.sub(r'^A\.\s*', '', re.sub(r'\s+', ' ', parts[1])).strip() if len(parts) > 1 else ""

        if not q:
            continue

        a, trailing_cat = strip_cat(a, from_end=True)
        out.append(f"\n**Q. {q}**")
        if a:
            out.append(f"**A.** {a}\n")

        if trailing_cat and trailing_cat != cur_cat:
            out.append(f"\n### {trailing_cat}\n")
            cur_cat = trailing_cat

    return "\n".join(out).strip()


# ── Fetch & convert URL (two-step) ────────────────────────────────────────────
def _fetch_page(url: str) -> tuple[BeautifulSoup, str, str]:
    """Lightweight fetch: URL → (soup, plain_text, content_hash)."""
    with httpx.Client(follow_redirects=True, timeout=20) as client:
        r = client.get(url, headers={"User-Agent": "Mozilla/5.0 (RAG-Bot/1.0)"})
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    plain_text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True)).strip()
    return soup, plain_text, _content_hash(plain_text)


def _convert_page(soup: BeautifulSoup, plain_text: str) -> str:
    """Heavy conversion: soup + plain_text → full markdown."""
    structure_md = _html_to_markdown(soup)
    qa_md        = _parse_qa(plain_text)
    return structure_md + ("\n\n---\n\n## Questions & Answers\n\n" + qa_md if qa_md else "")


# ── Find latest subfolder for a URL ──────────────────────────────────────────
def _find_latest_subfolder(path: str) -> Optional[str]:
    """Find the latest subfolder for the given path.

    Subfolders are named: {short_name}_{YYYYMMDD}_{HHMMSS}
    Sorting alphabetically by name gives chronological order.
    """
    name = _short_name(path)
    pattern = os.path.join(STORAGE_DIR, f"{name}_*")
    matches = sorted(glob.glob(pattern))
    # Filter to only directories
    matches = [m for m in matches if os.path.isdir(m)]
    return matches[-1] if matches else None


# ── Public API ────────────────────────────────────────────────────────────────
def get_stored_content_hash(url: str) -> str | None:
    """Return the content hash stored in the DB for this URL."""
    key = _make_index_key(url)
    return get_latest_content_hash(key)


async def build_index(
    base_url: str, path: str, openai_api_key: str,
    prefetched: tuple[BeautifulSoup, str, str] | None = None,
) -> dict:
    """Build FAISS L2 index inside a dated subfolder.

    Folder: .storage/{short_name}_{YYYYMMDD}_{HHMMSS}/
    Files:  index.faiss, metadata.json, content.md
    Old subfolders are kept for history.
    """
    full_url = base_url.rstrip("/") + "/" + path.lstrip("/")
    key    = _make_index_key(full_url)
    name   = _short_name(path)
    stamp  = _datetime_stamp()
    folder = os.path.join(STORAGE_DIR, f"{name}_{stamp}")
    os.makedirs(folder, exist_ok=True)

    index_path = os.path.join(folder, "index.faiss")
    meta_path  = os.path.join(folder, "metadata.json")
    md_path    = os.path.join(folder, "content.md")
    client     = AsyncOpenAI(api_key=openai_api_key)

    if prefetched is not None:
        soup, plain_text, content_hash = prefetched
    else:
        soup, plain_text, content_hash = await asyncio.to_thread(_fetch_page, full_url)

    markdown = _convert_page(soup, plain_text)
    chunks = _chunk_text(markdown)
    if not chunks:
        raise ValueError(f"No content extracted from {full_url}")

    # Save markdown
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Scraped Content\n\n**Source URL:** {full_url}  \n**Scraped At:** {now}  \n\n---\n\n{markdown}")

    # Embed chunks
    all_vecs = []
    for i in range(0, len(chunks), 100):
        all_vecs.append(await _embed(client, chunks[i:i + 100]))

    matrix = np.vstack(all_vecs)
    index  = faiss.IndexFlatL2(EMBED_DIM)
    index.add(matrix)
    faiss.write_index(index, index_path)

    # Save metadata
    metadata = {
        "base_url": base_url,
        "path": path,
        "url": full_url,
        "chunk_count": len(chunks),
        "md_path": md_path,
        "content_hash": content_hash,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "folder": folder,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # Save the new content hash to DB
    await asyncio.to_thread(save_content_hash, key, base_url, path, content_hash)

    return metadata


def load_index(url: str, path: str) -> Optional[tuple[faiss.Index, dict]]:
    """Load the latest FAISS index for the given path (by datetime in folder name)."""
    folder = _find_latest_subfolder(path)
    if folder is None:
        return None

    index_path = os.path.join(folder, "index.faiss")
    meta_path  = os.path.join(folder, "metadata.json")

    if not (os.path.exists(index_path) and os.path.exists(meta_path)):
        return None

    index = faiss.read_index(index_path)
    with open(meta_path, "r") as f:
        metadata = json.load(f)           # parse JSON → dict
    with open(metadata["md_path"], "r") as f:
        metadata["chunks"] = _chunk_text(f.read())
    return index, metadata                # returns proper dict


async def check_and_rebuild_if_changed(
    base_url: str, path: str, openai_api_key: str
) -> tuple[dict, bool]:
    """Fetch page, compare hash, rebuild index only if content changed.

    Returns (metadata, content_changed).
    Used by both the /scraping/init endpoint and the 24h scheduler.
    """
    full_url = base_url.rstrip("/") + "/" + path.lstrip("/")
    fetched = await asyncio.to_thread(_fetch_page, full_url)
    _, plain_text, new_hash = fetched
    old_hash = get_stored_content_hash(full_url)

    if old_hash == new_hash:
        result = load_index(full_url, path)
        if result is not None:
            _, metadata = result
            return metadata, False

    try:
        metadata = await build_index(
            base_url=base_url, path=path,
            openai_api_key=openai_api_key,
            prefetched=fetched,
        )
    except Exception:
        metadata = await build_index(
            base_url=base_url, path=path,
            openai_api_key=openai_api_key,
            prefetched=None,
        )
    return metadata, True


# Backward-compatible aliases
_embed_texts     = _embed
_parse_qa_blocks = _parse_qa