# ai_learning_api.py
"""
AI Learning Backend (single script)
- FastAPI endpoints:
  - POST   /documents/upload
  - GET    /documents
  - GET    /documents/{docid}
  - DELETE /documents/{docid}
  - POST   /documents/{docid}/prepare
  - POST   /documents/prepare-all
  - POST   /documents/prepare-selected
  - POST   /documents/delete-batch

Folders:
  data/
    registry.json
  storage/
    raw/
      <docid>_<original_filename>
    embeddings/
      <docid>/
        docling_full.json
        chunks.jsonl
        embeddings.npy
        embedding_meta.json
    indexes/
      <docid>/
        index.faiss
        index_metadata.json

Pipeline per doc:
  1) Docling convert PDF -> docling_full.json
  2) Semantic chunking (sections/lists/forms/checkboxes) -> chunks.jsonl
  3) OpenAI embeddings (text-embedding-3-small), L2 normalize -> embeddings.npy
  4) FAISS IndexFlatL2 -> index.faiss
  5) Metadata row -> chunk text + meta -> index_metadata.json

Requirements:
  pip install fastapi uvicorn python-multipart python-dotenv "openai>=1.0.0" faiss-cpu numpy docling

Env:
  export OPENAI_API_KEY="..."
"""
import os, sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Fix Windows symlink error: huggingface_hub tries to create symlinks
# which requires admin privileges on Windows. This tells it to not use symlinks.
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HUGGINGFACE_HUB_SYMLINKS"] = "false"
    
# from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import faiss
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi import Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from auth import router as auth_router
from dashboard import router as dashboard_router
from app_logger import get_logger
from fastapi.responses import JSONResponse

# db module requires pyodbc/MSSQL — make it optional
try:
    import db as dbmod
    _DB_AVAILABLE = True
except ImportError:
    dbmod = None
    _DB_AVAILABLE = False
from database import Base, engine

# OpenAI - optional (RAG features disabled without it)
try:
    from openai import OpenAI as _OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

# Docling - optional (document prepare disabled without it)
try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import PdfFormatOption, ImageFormatOption
    from docling.datamodel.base_models import InputFormat
    _DOCLING_AVAILABLE = True
except ImportError:
    _DOCLING_AVAILABLE = False
# ----------------------------
# CONFIG  (.env already loaded by config.py)
# ----------------------------

APP_NAME = "ai-learning"
LOG = get_logger(APP_NAME)

# Public base URL used to build clickable PDF URLs for citations.
# Example: https://yourdomain.com
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
def get_base_url(request: Request) -> str:
    """
    Returns the correct base URL for building document links.

    Priority:
    1. Use PUBLIC_BASE_URL from .env if provided
    2. Otherwise auto-detect from request (best for any laptop/server)
    """
    env_base = os.getenv("PUBLIC_BASE_URL", "").strip()

    if env_base:
        return env_base.rstrip("/")

    # Auto-detect IP + port from incoming request
    return str(request.base_url).rstrip("/")

# MSSQL connection string (pyodbc) must be set in env for DB integration.
# Example:
# MSSQL_CONN_STR='DRIVER={ODBC Driver 17 for SQL Server};SERVER=.;DATABASE=MyDb;UID=sa;PWD=...'

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"

RAW_DIR = STORAGE_DIR / "raw"
EMBED_DIR = STORAGE_DIR / "embeddings"
INDEX_DIR = STORAGE_DIR / "indexes"

REGISTRY_PATH = DATA_DIR / "registry.json"

EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 64
MAX_TOKENS = 800  # matches your semantic chunker token budget logic (approx)

client = _OpenAI() if _OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY") else None

# ----------------------------
# INIT DIRS
# ----------------------------

for d in [DATA_DIR, STORAGE_DIR, RAW_DIR, EMBED_DIR, INDEX_DIR]:
    d.mkdir(parents=True, exist_ok=True)

if not REGISTRY_PATH.exists():
    REGISTRY_PATH.write_text(json.dumps({"docs": {}}, indent=2), encoding="utf-8")


def _count_pdf_pages(file_path: Path) -> int:
    """Return number of pages in a PDF, or 0 on failure / non-PDF."""
    if file_path.suffix.lower() != ".pdf":
        return 0
    # Try pypdf first
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(file_path)).pages)
    except Exception:
        pass
    # Fallback: count /Type /Page entries (excluding /Type /Pages) via regex
    try:
        data = file_path.read_bytes()
        # Count objects that define a page (not the page-tree node)
        import re as _re
        count = len(_re.findall(rb'/Type\s*/Page(?!\s*s)\b', data))
        return count if count > 0 else 0
    except Exception:
        return 0


# ----------------------------
# REGISTRY HELPERS
# ----------------------------

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def load_registry() -> Dict[str, Any]:
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"docs": {}}


def save_registry(reg: Dict[str, Any]) -> None:
    REGISTRY_PATH.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")


def make_docid() -> str:
    # Short unique id, still safe enough for internal doc IDs
    return uuid.uuid4().hex[:12]


def sanitize_filename(name: str) -> str:
    # keep extension, remove path separators, normalize spaces
    name = name.replace("\\", "_").replace("/", "_")
    name = re.sub(r"\s+", " ", name).strip()
    return name


def find_raw_file_by_docid(docid: str) -> Optional[Path]:
    # raw file is saved as "<docid>_<original_filename>"
    candidates = list(RAW_DIR.glob(f"{docid}_*"))
    return candidates[0] if candidates else None

def build_public_raw_url(stored_name: str) -> str:
    """
    Builds a public URL to the stored raw file.
    UI can open PDFs directly using this URL.
    """
    if not PUBLIC_BASE_URL:
        # fallback: relative URL
        return f"/files/raw/{stored_name}"
    return f"{PUBLIC_BASE_URL}/files/raw/{stored_name}"

class ChatHistoryMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class RAGQueryRequest(BaseModel):
    userid: str = Field(..., min_length=1)
    sessionid: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    doc_ids: list[str] | None = None  # scope to specific docs (None = search all)
    history: list[ChatHistoryMessage] | None = None  # optional conversation history from frontend

class RAGSource(BaseModel):
    docid: str
    document_name: str
    url: str
    page: int | None = None
    chunk_id: str
    score: float | None = None
    excerpt: str

class RAGQueryResponse(BaseModel):
    answer: str
    sources: list[RAGSource]
    query_log_id: int | None = None

# ── Chat history + feedback models ───────────────────────────────────────────
class SessionPatchRequest(BaseModel):
    userid: str = Field(..., min_length=1)
    title: str | None = None
    is_favorite: bool | None = None

class FeedbackRequest(BaseModel):
    feedback: str | None = None  # 'like', 'dislike', or null

# ----------------------------
# SEMANTIC CHUNKER (adapted from your semanticchunker.py)
# ----------------------------

BULLET_CHARS = ["•", "·", "●", "▪", "", "o", "◦", "-"]
CHECKBOX_CHARS = ["□", "☐", "✓", "✔", "✗", "✘", ""]


def approx_tokens(text: str) -> int:
    text = text or ""
    return max(1, len(text) // 4)


def get_by_ref(doc: Dict[str, Any], ref_str: str) -> Any:
    """
    Resolve JSON-pointer style refs like '#/texts/314' or '#/groups/27'
    """
    if not ref_str.startswith("#/"):
        raise ValueError(f"Bad ref: {ref_str}")
    parts = ref_str[2:].split("/")
    obj: Any = doc
    for p in parts:
        if isinstance(obj, list):
            obj = obj[int(p)]
        else:
            obj = obj[p]
    return obj


def extract_pages_from_text(text_obj: Dict[str, Any]) -> set[int]:
    pages: set[int] = set()
    for prov in text_obj.get("prov", []):
        page_no = prov.get("page_no")
        if page_no is not None:
            pages.add(int(page_no))
    return pages


def build_source_entry(text_obj: Dict[str, Any], ref_str: str) -> Dict[str, Any]:
    return {
        "ref": text_obj.get("self_ref", ref_str),
        "label": text_obj.get("label"),
        "pages": sorted(extract_pages_from_text(text_obj)),
        "prov": text_obj.get("prov", []),
    }


def clean_leading_bullet(orig_or_text: str) -> str:
    s = (orig_or_text or "").lstrip()
    if not s:
        return s

    for ch in BULLET_CHARS + CHECKBOX_CHARS:
        if s.startswith(ch):
            return s[len(ch):].lstrip()

    s = re.sub(r"^[^\w\d]+", "", s).lstrip()
    return s


def format_list_item(text_obj: Dict[str, Any], indent_level: int) -> str:
    text = (text_obj.get("text") or "").strip()
    orig = (text_obj.get("orig") or "").strip()
    marker = (text_obj.get("marker") or "").strip()
    enumerated = bool(text_obj.get("enumerated"))
    indent = "    " * indent_level

    if enumerated and marker:
        line = f"{marker} {text}"
    else:
        base = clean_leading_bullet(orig) or text
        line = f"- {base}"

    return indent + line


def format_checkbox(text_obj: Dict[str, Any], indent_level: int) -> str:
    orig = (text_obj.get("orig") or "").strip()
    text = (text_obj.get("text") or "").strip()
    indent = "    " * indent_level

    base = clean_leading_bullet(orig) or clean_leading_bullet(text) or text
    label = text_obj.get("label") or ""
    box = "[x]" if "selected" in label else "[ ]"
    return f"{indent}{box} {base}"


def format_plain_text(text_obj: Dict[str, Any], indent_level: int) -> str:
    text = (text_obj.get("text") or "").strip()
    indent = "    " * indent_level
    return indent + text if text else ""


def build_group_unit(doc: Dict[str, Any], group_ref: str, current_section: Optional[Dict[str, Any]]):
    group_obj = get_by_ref(doc, group_ref)
    group_label = group_obj.get("label")
    group_name = group_obj.get("name")
    group_self_ref = group_obj.get("self_ref", group_ref)

    buf: List[str] = []
    pages: set[int] = set()
    sources: List[Dict[str, Any]] = []

    def walk(ref: str, indent_level: int):
        obj = get_by_ref(doc, ref)
        kind = ref.split("/")[1]

        if kind == "texts":
            if obj.get("content_layer") != "body":
                return

            t_label = obj.get("label")
            if t_label == "list_item":
                line = format_list_item(obj, indent_level)
            elif t_label and t_label.startswith("checkbox"):
                line = format_checkbox(obj, indent_level)
            else:
                line = format_plain_text(obj, indent_level)

            if line.strip():
                buf.append(line)
                pages.update(extract_pages_from_text(obj))
                sources.append(build_source_entry(obj, ref))

        elif kind == "groups":
            g_label = obj.get("label")
            child_indent = indent_level + 1 if g_label == "list" else indent_level
            for child in obj.get("children", []):
                walk(child["$ref"], child_indent)

        # ignore pictures/tables inside groups for now

    walk(group_ref, 0)

    text = "\n".join(buf).strip()
    if not text:
        return None

    meta = {
        "unit_type": "group",
        "group_label": group_label,
        "group_name": group_name,
        "group_ref": group_self_ref,
        "pages": sorted(pages),
        "section_title": current_section["title"] if current_section else None,
        "section_level": current_section["level"] if current_section else None,
        "sources": sources,
    }
    return {"text": text, "meta": meta}


def build_logical_units(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    body = doc["body"]
    body_children = body["children"]

    logical_units: List[Dict[str, Any]] = []

    inline_buf: List[str] = []
    inline_pages: set[int] = set()
    inline_sources: List[Dict[str, Any]] = []
    current_section: Optional[Dict[str, Any]] = None

    def flush_inline():
        nonlocal inline_buf, inline_pages, inline_sources
        if not inline_buf:
            return
        text = "\n".join(inline_buf).strip()
        if not text:
            inline_buf = []
            inline_pages = set()
            inline_sources = []
            return

        meta = {
            "unit_type": "inline",
            "pages": sorted(inline_pages),
            "section_title": current_section["title"] if current_section else None,
            "section_level": current_section["level"] if current_section else None,
            "sources": inline_sources,
        }
        logical_units.append({"text": text, "meta": meta})
        inline_buf = []
        inline_pages = set()
        inline_sources = []

    for child in body_children:
        ref = child["$ref"]
        kind = ref.split("/")[1]

        if kind == "texts":
            t_obj = get_by_ref(doc, ref)
            label = t_obj.get("label")
            content_layer = t_obj.get("content_layer")

            if content_layer != "body":
                continue

            if label == "section_header":
                flush_inline()
                header_text = (t_obj.get("text") or "").strip()
                if not header_text:
                    continue
                pages = extract_pages_from_text(t_obj)
                level = t_obj.get("level")

                section_meta = {
                    "unit_type": "section_header",
                    "pages": sorted(pages),
                    "section_title": header_text,
                    "section_level": level,
                    "sources": [build_source_entry(t_obj, ref)],
                }
                logical_units.append({"text": header_text, "meta": section_meta})

                current_section = {"title": header_text, "level": level, "pages": sorted(pages)}

            else:
                text = (t_obj.get("text") or "").strip()
                if text:
                    inline_buf.append(text)
                    inline_pages.update(extract_pages_from_text(t_obj))
                    inline_sources.append(build_source_entry(t_obj, ref))

        elif kind == "groups":
            flush_inline()
            unit = build_group_unit(doc, ref, current_section)
            if unit:
                logical_units.append(unit)

        elif kind == "pictures":
            flush_inline()
            pic_obj = get_by_ref(doc, ref)
            pic_pages: set[int] = set()
            for prov in pic_obj.get("prov", []):
                if prov.get("page_no") is not None:
                    pic_pages.add(int(prov["page_no"]))

            child_texts: List[str] = []
            sources: List[Dict[str, Any]] = []
            for ch in pic_obj.get("children", []):
                t_ref = ch["$ref"]
                t_obj = get_by_ref(doc, t_ref)
                text = (t_obj.get("text") or "").strip()
                if text:
                    child_texts.append(text)
                    sources.append(build_source_entry(t_obj, t_ref))

            if child_texts:
                description = "Image content: " + " ".join(child_texts)
                meta = {
                    "unit_type": "picture",
                    "pages": sorted(pic_pages),
                    "section_title": current_section["title"] if current_section else None,
                    "section_level": current_section["level"] if current_section else None,
                    "sources": sources,
                }
                logical_units.append({"text": description, "meta": meta})

        else:
            flush_inline()

    flush_inline()
    return logical_units


def split_large_unit(text: str, max_tokens: int) -> List[str]:
    lines = text.split("\n")
    segments: List[str] = []
    buf: List[str] = []

    for line in lines:
        tentative = buf + [line]
        if approx_tokens("\n".join(tentative)) > max_tokens and buf:
            segments.append("\n".join(buf).strip())
            buf = [line]
        else:
            buf.append(line)

    if buf:
        segments.append("\n".join(buf).strip())

    return [s for s in segments if s.strip()]


def units_to_chunks(units: List[Dict[str, Any]], max_tokens: int, doc_name: str, doc_filename: str) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    cur_texts: List[str] = []
    cur_metas: List[Dict[str, Any]] = []

    def flush():
        nonlocal cur_texts, cur_metas
        if not cur_texts:
            return
        combined = "\n\n".join(cur_texts).strip()
        if not combined:
            cur_texts, cur_metas = [], []
            return

        pages: set[int] = set()
        unit_types: set[str] = set()
        group_labels: set[str] = set()
        section_titles: set[str] = set()
        all_sources: List[Dict[str, Any]] = []

        for m in cur_metas:
            pages.update(m.get("pages", []) or [])
            if m.get("unit_type"):
                unit_types.add(m["unit_type"])
            if m.get("group_label"):
                group_labels.add(m["group_label"])
            if m.get("section_title"):
                section_titles.add(m["section_title"])
            all_sources.extend(m.get("sources", []) or [])

        chunk_meta = {
            "pages": sorted(pages),
            "unit_count": len(cur_metas),
            "unit_types": sorted(unit_types),
            "group_labels": sorted(group_labels),
            "section_titles": sorted(section_titles),
            "sources": all_sources,
            "doc_name": doc_name,
            "doc_filename": doc_filename,
            "units": cur_metas,
        }

        chunks.append({"id": len(chunks), "text": combined, "meta": chunk_meta})
        cur_texts, cur_metas = [], []

    for unit in units:
        text = unit["text"]
        meta = unit["meta"]
        t_tokens = approx_tokens(text)

        if t_tokens > max_tokens:
            flush()
            segments = split_large_unit(text, max_tokens)
            for idx, seg in enumerate(segments):
                seg_meta = dict(meta)
                seg_meta["fragment_index"] = idx
                chunks.append({
                    "id": len(chunks),
                    "text": seg,
                    "meta": {
                        "pages": seg_meta.get("pages", []),
                        "unit_count": 1,
                        "unit_types": [seg_meta.get("unit_type")],
                        "group_labels": [seg_meta["group_label"]] if seg_meta.get("group_label") else [],
                        "section_titles": [seg_meta["section_title"]] if seg_meta.get("section_title") else [],
                        "sources": seg_meta.get("sources", []),
                        "doc_name": doc_name,
                        "doc_filename": doc_filename,
                        "units": [seg_meta],
                    },
                })
            continue

        tentative = "\n\n".join(cur_texts + [text])
        if approx_tokens(tentative) > max_tokens and cur_texts:
            flush()

        cur_texts.append(text)
        cur_metas.append(meta)

    flush()
    return chunks


# ----------------------------
# EMBEDDING + INDEX HELPERS
# ----------------------------

def normalize_embeddings(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def embed_texts_openai(texts: List[str], model: str) -> np.ndarray:
    all_embeddings: List[List[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        resp = client.embeddings.create(model=model, input=batch)
        batch_embs = [item.embedding for item in resp.data]
        all_embeddings.extend(batch_embs)
    return np.array(all_embeddings, dtype="float32")


def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatL2:
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)
    return index


# ----------------------------
# PIPELINE (per docid)
# ----------------------------

# def prepare_doc(docid: str) -> Dict[str, Any]:
#     raw_path = find_raw_file_by_docid(docid)
#     if not raw_path or not raw_path.exists():
#         raise HTTPException(status_code=404, detail=f"Raw file for docid '{docid}' not found")

#     # output folders
#     doc_embed_dir = EMBED_DIR / docid
#     doc_index_dir = INDEX_DIR / docid
#     doc_embed_dir.mkdir(parents=True, exist_ok=True)
#     doc_index_dir.mkdir(parents=True, exist_ok=True)

#     # 1) Docling convert
#     converter = DocumentConverter()
#     result = converter.convert(str(raw_path))
#     doc_dict = result.document.export_to_dict()

#     docling_json_path = doc_embed_dir / "docling_full.json"
#     docling_json_path.write_text(json.dumps(doc_dict, indent=2, ensure_ascii=False), encoding="utf-8")


def prepare_doc(docid: str) -> Dict[str, Any]:
    if not _DOCLING_AVAILABLE:
        raise HTTPException(status_code=503, detail="Docling is not installed. Document preparation is unavailable.")
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured. Document preparation is unavailable.")

    raw_path = find_raw_file_by_docid(docid)
    if not raw_path or not raw_path.exists():
        raise HTTPException(status_code=404, detail=f"Raw file for docid '{docid}' not found")

    # Output folders setup
    doc_embed_dir = EMBED_DIR / docid
    doc_index_dir = INDEX_DIR / docid
    doc_embed_dir.mkdir(parents=True, exist_ok=True)
    doc_index_dir.mkdir(parents=True, exist_ok=True)

    # --- IMAGE FORMAT DETECTION ---
    # If the file is an image, use ImageFormatOption directly with OCR + 2x upscaling.
    # This bypasses the PDF 2-pass strategy entirely — images have no text layer to try.
    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
    if raw_path.suffix.lower() in IMAGE_EXTS:
        LOG.info(f"Image file detected for {docid}. Using ImageFormatOption with OCR...")
        img_pipeline_options = PdfPipelineOptions()
        img_pipeline_options.do_ocr = True
        img_pipeline_options.do_table_structure = True
        img_pipeline_options.images_scale = 2.0

        img_converter = DocumentConverter(
            format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=img_pipeline_options)}
        )
        try:
            result = img_converter.convert(str(raw_path))
        except OSError as e:
            if "WinError 1314" in str(e) or "privilege" in str(e).lower():
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Windows symlink error: Enable Developer Mode in "
                        "Settings > Privacy & Security > For Developers, "
                        "or run the backend as Administrator."
                    ),
                )
            raise
        doc_dict = result.document.export_to_dict()
        LOG.info(f"Image extraction complete for {docid}.")

    else:
        # --- THE SMART STRATEGY (PDF only) ---

        # STEP 1: Try the "Fast Path" (Digital Extraction Only)
        # This works perfectly for 90% of PDFs (like your SOP file).
        # It takes ~5 seconds and ignores the "garbage" images that cause errors.

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False  # Start with OCR OFF
        pipeline_options.do_table_structure = True

        converter = DocumentConverter(
            format_options={"pdf": PdfFormatOption(pipeline_options=pipeline_options)}
        )

        LOG.info(f"Attempting Fast Extraction for {docid}...")
        try:
            result = converter.convert(str(raw_path))
        except OSError as e:
            if "WinError 1314" in str(e) or "privilege" in str(e).lower():
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Windows symlink error: Enable Developer Mode in "
                        "Settings > Privacy & Security > For Developers, "
                        "or run the backend as Administrator."
                    ),
                )
            raise
        doc_dict = result.document.export_to_dict()

        # STEP 2: The "Intelligent Check"
        # We check: Did we actually get any text?
        text_content = ""
        if doc_dict.get("body") and doc_dict["body"].get("children"):
            # Verify if we extracted meaningful text (not just empty structure)
            # We can iterate briefly to check for actual text strings
            pass

        # Logic: If the Fast Path returned an empty body, it MUST be a scanned file.
        # ONLY THEN do we turn on the slow OCR engine.
        if not doc_dict.get("body") or not doc_dict["body"].get("children"):
            LOG.warning(f"Fast extraction found no text for {docid}. Retrying with OCR enabled (Slow Mode)...")

            # Enable OCR now
            pipeline_options.do_ocr = True
            converter = DocumentConverter(
                format_options={"pdf": PdfFormatOption(pipeline_options=pipeline_options)}
            )
            result = converter.convert(str(raw_path))
            doc_dict = result.document.export_to_dict()
        else:
            LOG.info(f"Fast extraction successful for {docid}. Skipping OCR.")

    # --- END STRATEGY ---

    # Save results (rest of your code...)
    docling_json_path = doc_embed_dir / "docling_full.json"
    docling_json_path.write_text(json.dumps(doc_dict, indent=2, ensure_ascii=False), encoding="utf-8")


    # 2) Semantic chunking
    units = build_logical_units(doc_dict)
    doc_name = doc_dict.get("name") or ""
    doc_filename = doc_dict.get("origin", {}).get("filename") or raw_path.name

    chunks = units_to_chunks(units, MAX_TOKENS, doc_name, doc_filename)

    chunks_jsonl_path = doc_embed_dir / "chunks.jsonl"
    with chunks_jsonl_path.open("w", encoding="utf-8") as f:
        for ch in chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")

    # 3) Embeddings
    texts = [c["text"] for c in chunks]
    if not texts:
        raise HTTPException(status_code=400, detail=f"No chunks produced for docid '{docid}'")

    embeddings = embed_texts_openai(texts, EMBEDDING_MODEL)
    embeddings = normalize_embeddings(embeddings)

    embeddings_npy_path = doc_embed_dir / "embeddings.npy"
    np.save(str(embeddings_npy_path), embeddings)

    # (optional) embedding meta
    embedding_meta = {
        "docid": docid,
        "embedding_model": EMBEDDING_MODEL,
        "chunk_count": len(chunks),
        "embedding_shape": list(embeddings.shape),
        "created_at": _now_iso(),
    }
    (doc_embed_dir / "embedding_meta.json").write_text(
        json.dumps(embedding_meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 4) FAISS index
    index = build_faiss_index(embeddings)
    index_path = doc_index_dir / "index.faiss"
    faiss.write_index(index, str(index_path))

    # 5) Index metadata row -> chunk
    index_metadata = [
        {
            "row": i,
            "chunk_id": c.get("chunk_id") or str(i),
            "text": c["text"],
            "pages": c.get("pages", []),
            "meta": c.get("meta", {}),
        }
        for i, c in enumerate(chunks)
    ]
    index_metadata_path = doc_index_dir / "index_metadata.json"
    index_metadata_path.write_text(json.dumps(index_metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    # Compute total page count from chunk page lists
    all_pages: set[int] = set()
    for c in chunks:
        all_pages.update(c.get("pages") or [])
    total_pages = max(all_pages) if all_pages else 0

    # Update registry status
    reg = load_registry()
    if docid in reg["docs"]:
        reg["docs"][docid]["prepared"] = True
        reg["docs"][docid]["prepared_at"] = _now_iso()
        reg["docs"][docid]["chunk_count"] = len(chunks)
        reg["docs"][docid]["pages"] = total_pages
        save_registry(reg)

    # Persist document + chunks to DB (optional)
    try:
        if os.getenv("MSSQL_CONN_STR", "").strip():
            public_url = build_public_raw_url(raw_path.name)
            with dbmod.get_conn() as conn:
                dbmod.upsert_document(conn, {
                    "DocumentId": docid,
                    "OriginalName": reg.get("docs", {}).get(docid, {}).get("original_filename", raw_path.name),
                    "StoredName": raw_path.name,
                    "MimeType": "application/pdf" if raw_path.suffix.lower()==".pdf" else None,
                    "SizeBytes": raw_path.stat().st_size if raw_path.exists() else None,
                    "RawPath": str(raw_path),
                    "PublicUrl": public_url,
                    "Prepared": True,
                    "ChunkCount": len(chunks),
                    "PreparedAtUtc": datetime.utcnow(),
                })
                # Store chunk text + page mapping for UI citations
                db_chunks = []
                for c in chunks:
                    cc = dict(c)
                    cc["chunk_id"] = cc.get("chunk_id") or str(cc.get("id"))
                    db_chunks.append(cc)
                dbmod.replace_document_chunks(conn, docid, db_chunks)
                conn.commit()
    except Exception as ex:
        LOG.error(f"DB persist failed for prepared doc {docid}: {ex}")


    return {
        "docid": docid,
        "raw_file": raw_path.name,
        "chunks": len(chunks),
        "embeddings_path": str(doc_embed_dir),
        "index_path": str(doc_index_dir),
    }


def prepare_all_docs() -> Dict[str, Any]:
    processed: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    # Discover raw docs by filename pattern: "<docid>_..."
    for raw_file in sorted(RAW_DIR.glob("*_*")):
        docid = raw_file.name.split("_", 1)[0].strip()
        if not docid:
            continue

        # Ensure registry has it (in case files were dropped into raw manually)
        reg = load_registry()
        if docid not in reg["docs"]:
            reg["docs"][docid] = {
                "docid": docid,
                "original_filename": raw_file.name.split("_", 1)[1],
                "stored_filename": raw_file.name,
                "created_at": _now_iso(),
                "prepared": False,
            }
            save_registry(reg)

        try:
            out = prepare_doc(docid)
            processed.append(out)
        except Exception as e:
            failed.append({"docid": docid, "error": str(e)})

    return {"processed": processed, "failed": failed, "raw_count": len(list(RAW_DIR.glob("*_*")))}


def delete_doc(docid: str) -> Dict[str, Any]:
    reg = load_registry()
    raw_path = find_raw_file_by_docid(docid)

    deleted = {"raw": False, "embeddings": False, "indexes": False, "registry": False}

    # delete raw
    if raw_path and raw_path.exists():
        raw_path.unlink()
        deleted["raw"] = True

    # delete embeddings folder
    doc_embed_dir = EMBED_DIR / docid
    if doc_embed_dir.exists():
        shutil.rmtree(doc_embed_dir, ignore_errors=True)
        deleted["embeddings"] = True

    # delete index folder
    doc_index_dir = INDEX_DIR / docid
    if doc_index_dir.exists():
        shutil.rmtree(doc_index_dir, ignore_errors=True)
        deleted["indexes"] = True

    # remove registry entry
    if docid in reg.get("docs", {}):
        reg["docs"].pop(docid, None)
        save_registry(reg)
        deleted["registry"] = True

    if not any(deleted.values()):
        raise HTTPException(status_code=404, detail=f"Nothing found to delete for docid '{docid}'")


    # DB delete (optional)
    try:
        if os.getenv("MSSQL_CONN_STR", "").strip():
            with dbmod.get_conn() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM dbo.DocumentChunks WHERE DocumentId=?", docid)
                cur.execute("DELETE FROM dbo.Documents WHERE DocumentId=?", docid)
                conn.commit()
    except Exception as ex:
        LOG.error(f"DB delete failed for {docid}: {ex}")

    return {"docid": docid, "deleted": deleted}


# ----------------------------
# FASTAPI APP + ENDPOINTS
# ----------------------------

app = FastAPI(title=APP_NAME)
@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)
    
app.include_router(auth_router)
app.include_router(dashboard_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://192.168.1.153:4200",
    ],
    allow_credentials=True,   # set True only if you use cookies/session auth
    allow_methods=["*"],
    allow_headers=["*"],
)
# Serve uploaded raw files so UI can open PDFs via URL
app.mount("/files", StaticFiles(directory=str(STORAGE_DIR)), name="files")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = datetime.utcnow()
    try:
        response = await call_next(request)
        dur_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        LOG.info(f"{request.method} {request.url.path} -> {response.status_code} ({dur_ms}ms)")
        return response
    except Exception as ex:
        dur_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        LOG.error(f"ERROR {request.method} {request.url.path} ({dur_ms}ms): {ex}")
        raise

@app.on_event("startup")
def on_startup():
    # Initialize MSSQL schema if configured
    try:
        if os.getenv("MSSQL_CONN_STR", "").strip() and dbmod:
            dbmod.init_db()
            LOG.info("DB initialized/verified.")
        else:
            LOG.warning("MSSQL_CONN_STR not set; DB integration is disabled.")
    except Exception as ex:
        LOG.error(f"DB init failed: {ex}")



@app.get("/health")
def health():
    return {"ok": True, "app": APP_NAME, "time": _now_iso()}
@app.get("/debug/env")
def debug_env():
    keys = [
        "HF_HUB_DISABLE_SYMLINKS",
        "HF_HOME",
        "HUGGINGFACE_HUB_CACHE",
        "TRANSFORMERS_CACHE",
        "USERPROFILE",
        "HOME",
    ]
    return {k: os.getenv(k) for k in keys}

# ── Document Categories ──────────────────────────────────────────────────────
# Returns categories from MSSQL dbo.DocumentCategories if available,
# otherwise returns a default set for the demo.
@app.get("/categories")
def get_categories():
    # Try loading from DB first
    try:
        if os.getenv("MSSQL_CONN_STR", "").strip() and dbmod:
            with dbmod.get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT category_id, category_name, description "
                    "FROM dbo.DocumentCategories ORDER BY category_name"
                )
                rows = cursor.fetchall()
                if rows:
                    return {
                        "categories": [
                            {
                                "category_id": r[0],
                                "category_name": r[1],
                                "description": r[2] or "",
                            }
                            for r in rows
                        ]
                    }
    except Exception as ex:
        LOG.warning(f"Could not load categories from DB: {ex}")

    # Fallback: return default categories
    return {
        "categories": [
            {"category_id": 1, "category_name": "HR Policies", "description": "Human Resources policies and guidelines"},
            {"category_id": 2, "category_name": "Technical Docs", "description": "Technical documentation and guides"},
            {"category_id": 3, "category_name": "Training Materials", "description": "Training and onboarding materials"},
            {"category_id": 4, "category_name": "SOPs", "description": "Standard Operating Procedures"},
            {"category_id": 5, "category_name": "General", "description": "General documents"},
        ]
    }

@app.post("/documents/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    category_name: str = Form(None),
    category_id: str = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    original = sanitize_filename(file.filename)
    docid = make_docid()
    stored_name = f"{docid}_{original}"
    stored_path = RAW_DIR / stored_name

    # Save locally
    try:
        content = await file.read()
        stored_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store file: {e}")

    # Update registry
    reg = load_registry()
    reg["docs"][docid] = {
        "docid": docid,
        "original_filename": original,
        "stored_filename": stored_name,
        "created_at": _now_iso(),
        "prepared": False,
        "category_name": category_name,
        "category_id": category_id,
        "size": stored_path.stat().st_size if stored_path.exists() else 0,
        "pages": _count_pdf_pages(stored_path),
    }
    save_registry(reg)


    # DB upsert (optional if MSSQL_CONN_STR configured)
    base_url = get_base_url(request)
    public_url = f"{base_url}/files/raw/{stored_name}"
    try:
        if os.getenv("MSSQL_CONN_STR", "").strip():
            with dbmod.get_conn() as conn:
                dbmod.upsert_document(conn, {
                    "DocumentId": docid,
                    "OriginalName": original,
                    "StoredName": stored_name,
                    "MimeType": file.content_type,
                    "SizeBytes": stored_path.stat().st_size if stored_path.exists() else None,
                    "RawPath": str(stored_path),
                    "PublicUrl": public_url,
                    "Prepared": False,
                    "ChunkCount": None,
                    "PreparedAtUtc": None,
                    "CategoryName": category_name,
                    "CategoryId": category_id,
                })
                conn.commit()
    except Exception as ex:
        LOG.error(f"DB upsert_document failed for {docid}: {ex}")

    return {
        "docid": docid,
        "stored_filename": stored_name,
        "raw_path": str(stored_path),
        "public_url": public_url,
        "category_name": category_name,
        "category_id": category_id,
    }


@app.get("/documents")
def list_documents(category: str = None):
    reg = load_registry()
    docs = list(reg.get("docs", {}).values())
    # Filter by category if provided
    if category:
        docs = [d for d in docs if category in (d.get("category_name") or "").split(",")]
    # Enrich with file size and page count if missing
    dirty = False
    for doc in docs:
        if not doc.get("size"):
            raw = find_raw_file_by_docid(doc["docid"])
            doc["size"] = raw.stat().st_size if raw and raw.exists() else 0
        if not doc.get("pages"):
            # Count pages directly from the raw PDF file
            raw = find_raw_file_by_docid(doc["docid"])
            if raw and raw.exists():
                doc["pages"] = _count_pdf_pages(raw)
                if doc["pages"] and doc["docid"] in reg.get("docs", {}):
                    reg["docs"][doc["docid"]]["pages"] = doc["pages"]
                    dirty = True
    if dirty:
        save_registry(reg)
    # stable ordering by created time if present
    docs.sort(key=lambda d: d.get("created_at", ""))
    return {"count": len(docs), "docs": docs}


@app.get("/documents/{docid}")
def get_document(docid: str):
    reg = load_registry()
    doc = reg.get("docs", {}).get(docid)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Docid '{docid}' not found")
    raw_file = find_raw_file_by_docid(docid)
    return {
        "doc": doc,
        "raw_exists": bool(raw_file and raw_file.exists()),
        "embeddings_exists": (EMBED_DIR / docid).exists(),
        "indexes_exists": (INDEX_DIR / docid).exists(),
    }


@app.delete("/documents/{docid}")
def delete_document(docid: str):
    return delete_doc(docid)


@app.post("/documents/{docid}/prepare")
def prepare_single(docid: str):
    # runs extraction + embedding + indexing for that docid
    out = prepare_doc(docid)
    return {"status": "prepared", "result": out}


@app.post("/documents/prepare-all")
def prepare_all():
    out = prepare_all_docs()
    return {"status": "done", **out}


class PrepareSelectedRequest(BaseModel):
    doc_ids: list[str] = Field(..., min_length=1)


@app.post("/documents/prepare-selected")
def prepare_selected(payload: PrepareSelectedRequest):
    """Prepare only the documents whose IDs are in doc_ids."""
    processed = []
    failed = []
    for docid in payload.doc_ids:
        try:
            out = prepare_doc(docid)
            processed.append(out)
        except Exception as e:
            failed.append({"docid": docid, "error": str(e)})
    return {"status": "done", "processed": processed, "failed": failed}


class DeleteBatchRequest(BaseModel):
    doc_ids: list[str] = Field(..., min_length=1)


@app.post("/documents/delete-batch")
def delete_batch(payload: DeleteBatchRequest):
    """Delete multiple documents by their IDs."""
    deleted = []
    failed = []
    for docid in payload.doc_ids:
        try:
            out = delete_doc(docid)
            deleted.append({"docid": docid, **out})
        except Exception as e:
            failed.append({"docid": docid, "error": str(e)})
    return {"status": "done", "deleted": deleted, "failed": failed}


# ----------------------------
# RUN (optional convenience)
# ----------------------------

# ----------------------------
# RAG QUERY ENDPOINT
# ----------------------------

CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "1"))
RAG_PER_DOC_K = int(os.getenv("RAG_PER_DOC_K", "6"))

_INDEX_CACHE: dict[str, dict[str, Any]] = {}

def _load_faiss_index(docid: str) -> tuple[faiss.Index, list[dict[str, Any]]]:
    """
    Loads FAISS index + metadata for a prepared doc. Uses a simple in-memory cache.
    """
    idx_path = (INDEX_DIR / docid / "index.faiss")
    meta_path = (INDEX_DIR / docid / "index_metadata.json")
    if not idx_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"Index not found for docid {docid}")

    key = docid
    mtime = max(idx_path.stat().st_mtime, meta_path.stat().st_mtime)
    cached = _INDEX_CACHE.get(key)
    if cached and cached.get("mtime") == mtime:
        return cached["index"], cached["meta"]

    index = faiss.read_index(str(idx_path))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    _INDEX_CACHE[key] = {"mtime": mtime, "index": index, "meta": meta}
    return index, meta

def _get_prepared_docids() -> list[str]:
    reg = load_registry()
    docids = []
    for docid, d in (reg.get("docs") or {}).items():
        if d.get("prepared"):
            docids.append(docid)
    return docids

def _search_across_docs(query_vec: np.ndarray, top_k: int = RAG_TOP_K, per_doc_k: int = RAG_PER_DOC_K, doc_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Returns merged results: [{docid, score, metaRow, rowIndex}]
    For IndexFlatL2, smaller distance is better.
    When doc_ids is provided, only those documents are searched.
    """
    results: list[dict[str, Any]] = []
    target_ids = doc_ids if doc_ids else _get_prepared_docids()
    for docid in target_ids:
        try:
            index, meta = _load_faiss_index(docid)
            D, I = index.search(query_vec.astype("float32"), per_doc_k)
            for dist, row in zip(D[0].tolist(), I[0].tolist()):
                if row < 0 or row >= len(meta): 
                    continue
                results.append({
                    "docid": docid,
                    "distance": float(dist),
                    "row": int(row),
                    "meta": meta[row],
                })
        except Exception as ex:
            LOG.error(f"RAG index load/search failed for {docid}: {ex}")

    results.sort(key=lambda r: r["distance"])
    return results[:top_k]

def _build_context_and_sources(hits: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """
    Builds model context and UI-ready sources.
    """
    reg = load_registry()
    contexts = []
    sources: list[dict[str, Any]] = []

    for i, h in enumerate(hits, start=1):
        docid = h["docid"]
        meta = h["meta"] or {}
        chunk_text = (meta.get("text") or "").strip()
        pages = meta.get("pages") or meta.get("meta", {}).get("pages") or []
        page = pages[0] if pages else None

        doc_info = (reg.get("docs") or {}).get(docid) or {}
        stored_name = doc_info.get("stored_filename") or f"{docid}"
        original_name = doc_info.get("original_filename") or stored_name

        base_url = build_public_raw_url(stored_name)
        url = f"{base_url}#page={page}" if page else base_url

        excerpt = chunk_text[:800]

        sources.append({
            "docid": docid,
            "document_name": original_name,
            "url": url,
            "page": page,
            "chunk_id": meta.get("chunk_id") or str(meta.get("row") or ""),
            "score": h.get("distance"),
            "excerpt": excerpt,
        })

        contexts.append(f"[Source {i}] (doc={original_name}, page={page})\n{excerpt}\n")

    return "\n".join(contexts), sources

def _generate_answer(query: str, context: str, conversation_history: list[dict] | None = None) -> str:
    """
    Generates a grounded answer using retrieved context and optional conversation history.
    """
    system = (
        "You are a helpful assistant. Answer ONLY using the provided sources. "
        "If the answer isn't in the sources, say you don't know. "
        "Do not invent page numbers. "
        "If the user asks a follow-up question, use the conversation history to understand what they are referring to."
    )

    messages: list[dict] = [{"role": "system", "content": system}]

    # Include recent conversation history for follow-up context (last 5 exchanges)
    if conversation_history:
        for msg in conversation_history[-10:]:  # up to 5 Q&A pairs = 10 messages
            role = "user" if msg["type"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["text"]})

    user = f"Question:\n{query}\n\nSources:\n{context}\n\nReturn a helpful answer."
    messages.append({"role": "user", "content": user})

    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()

@app.post("/rag/query", response_model=RAGQueryResponse)
async def rag_query(payload: RAGQueryRequest, request: Request):
    """
    Input: { userid, sessionid, query }
    Output: { answer, sources:[{docid,document_name,url,page,chunk_id,score,excerpt}, ...] }

    The UI can open the PDF at the exact page using `url` which contains `#page=<n>` when available.
    """
    try:
        if not client:
            raise HTTPException(status_code=503, detail="OpenAI API key not configured. RAG queries are unavailable.")

        q = (payload.query or "").strip()
        if not q:
            raise HTTPException(status_code=400, detail="query is required")

        # Ensure session exists in DB (optional)
        try:
            if os.getenv("MSSQL_CONN_STR", "").strip():
                with dbmod.get_conn() as conn:
                    dbmod.upsert_session(conn, payload.userid, payload.sessionid)
                    conn.commit()
        except Exception as ex:
            LOG.error(f"DB upsert_session failed: {ex}")

        # Retrieve conversation history for follow-up context
        # Priority: DB history > frontend-supplied history
        conversation_history: list[dict] = []
        try:
            if os.getenv("MSSQL_CONN_STR", "").strip():
                with dbmod.get_conn() as conn:
                    conversation_history = dbmod.get_session_messages(conn, payload.userid, payload.sessionid)
        except Exception as ex:
            LOG.warning(f"Could not retrieve session history for follow-up context: {ex}")

        # Fallback to frontend-supplied history if DB history is empty
        if not conversation_history and payload.history:
            conversation_history = [
                {"type": "user" if m.role == "user" else "bot", "text": m.content}
                for m in payload.history
            ]

        # Embed query
        q_emb = embed_texts_openai([q], EMBEDDING_MODEL)
        q_emb = normalize_embeddings(q_emb)
        hits = _search_across_docs(q_emb, top_k=RAG_TOP_K, per_doc_k=RAG_PER_DOC_K, doc_ids=payload.doc_ids)
        context, sources = _build_context_and_sources(hits)
        if not sources:
            answer = "I don't know based on the currently uploaded documents."
        else:
            answer = _generate_answer(q, context, conversation_history if conversation_history else None)

        # Store query log + citations (optional)
        qid = None
        try:
            if os.getenv("MSSQL_CONN_STR", "").strip():
                sources_json_str = json.dumps(sources) if sources else None
                with dbmod.get_conn() as conn:
                    qid = dbmod.insert_query_log(conn, payload.userid, payload.sessionid, q, answer, CHAT_MODEL, sources_json_str)
                    for s in sources:
                        dbmod.insert_citation(
                            conn,
                            qid,
                            s["docid"],
                            s["chunk_id"],
                            s.get("page"),
                            float(s["score"]) if s.get("score") is not None else None,
                            (s.get("excerpt") or "")[:2000],
                        )
                    conn.commit()
        except Exception as ex:
            LOG.error(f"DB insert query/citations failed: {ex}")

        # Enforce max 3 sources in response
        sources = sources[:3]
        LOG.info(f"RAG query user={payload.userid} session={payload.sessionid} hits={len(sources)} path={request.url.path}")
        return {"answer": answer, "sources": sources, "query_log_id": qid}
    except HTTPException:
        raise
    except Exception as ex:
        LOG.error(f"Unhandled error in /rag/query: {ex}")
        raise HTTPException(status_code=500, detail="Internal server error")

# ── Chat History Endpoints ───────────────────────────────────────────────────

@app.get("/chat/sessions")
async def list_chat_sessions(userid: str):
    """List all chat sessions for a user."""
    try:
        with dbmod.get_conn() as conn:
            sessions = dbmod.get_user_sessions(conn, userid)
        return {"sessions": sessions}
    except Exception as ex:
        LOG.error(f"Error listing sessions: {ex}")
        raise HTTPException(status_code=500, detail="Failed to list sessions")


@app.get("/chat/sessions/{session_id}/messages")
async def get_chat_messages(session_id: str, userid: str):
    """Get all messages for a specific session."""
    try:
        with dbmod.get_conn() as conn:
            messages = dbmod.get_session_messages(conn, userid, session_id)
        return {"messages": messages}
    except Exception as ex:
        LOG.error(f"Error fetching messages: {ex}")
        raise HTTPException(status_code=500, detail="Failed to fetch messages")


@app.patch("/chat/sessions/{session_id}")
async def update_chat_session(session_id: str, payload: SessionPatchRequest):
    """Update session title and/or favorite status."""
    try:
        with dbmod.get_conn() as conn:
            if payload.title is not None:
                dbmod.update_session_title(conn, payload.userid, session_id, payload.title)
            if payload.is_favorite is not None:
                dbmod.update_session_favorite(conn, payload.userid, session_id, payload.is_favorite)
            conn.commit()
        return {"success": True}
    except Exception as ex:
        LOG.error(f"Error updating session: {ex}")
        raise HTTPException(status_code=500, detail="Failed to update session")


@app.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str, userid: str):
    """Delete a session and all its messages."""
    try:
        with dbmod.get_conn() as conn:
            dbmod.delete_session(conn, userid, session_id)
            conn.commit()
        return {"success": True}
    except Exception as ex:
        LOG.error(f"Error deleting session: {ex}")
        raise HTTPException(status_code=500, detail="Failed to delete session")


@app.post("/chat/messages/{query_log_id}/feedback")
async def set_message_feedback(query_log_id: int, payload: FeedbackRequest):
    """Set like/dislike feedback on a bot message."""
    try:
        with dbmod.get_conn() as conn:
            dbmod.update_query_feedback(conn, query_log_id, payload.feedback)
            conn.commit()
        return {"success": True}
    except Exception as ex:
        LOG.error(f"Error setting feedback: {ex}")
        raise HTTPException(status_code=500, detail="Failed to set feedback")


if __name__ == "__main__":
    import uvicorn
    from config import settings as _cfg
    uvicorn.run("pipeline:app", host=_cfg.HOST, port=_cfg.PORT, reload=_cfg.RELOAD)



# pip install fastapi uvicorn python-multipart python-dotenv "openai>=1.0.0" faiss-cpu numpy docling
# export OPENAI_API_KEY="YOUR_KEY"
# python ai_learning_api.py