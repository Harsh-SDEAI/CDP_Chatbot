"""
Business logic: Admin FAISS indexing, document processing (docling),
storage helpers, KB export, and LlamaIndex chatbot engine.
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
from bs4 import BeautifulSoup
from openai import OpenAI

from config import (
    OPENAI_API_KEY, STORAGE_DIR, IMAGES_DIR,
    FAISS_INDEX_PATH, FAISS_META_PATH, EMBEDDING_DIM,
    TEXT_FOLDER, SAVE_PATH, MAX_FILE_SIZE, BASE_FILE_NAME,
    get_db_connection, clean_text,
)

# ── Docling imports (PDF / image OCR) ─────────────────────────────────────────
from docling.document_converter import DocumentConverter, PdfFormatOption, ImageFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions

# ── LlamaIndex imports (chatbot engine) ───────────────────────────────────────
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, load_index_from_storage
from llama_index.vector_stores.faiss import FaissVectorStore
from llama_index.llms.openai import OpenAI as LlamaOpenAI
from llama_index.embeddings.openai import OpenAIEmbedding

# ═══════════════════════════════════════════════════════════════════════════════
#  ADMIN FAISS INDEX  (raw FAISS + text-embedding-3-small, 1536-dim)
# ═══════════════════════════════════════════════════════════════════════════════

ai = OpenAI()  # uses OPENAI_API_KEY from env

_faiss_index: Optional[faiss.IndexFlatL2] = None
_faiss_meta: List[Dict[str, Any]] = []


def load_admin_faiss():
    global _faiss_index, _faiss_meta
    if FAISS_INDEX_PATH.exists() and FAISS_META_PATH.exists():
        _faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
        _faiss_meta = json.loads(FAISS_META_PATH.read_text(encoding="utf-8"))
        print(f"[FAISS] Loaded index with {_faiss_index.ntotal} vectors.")
    else:
        _faiss_index = faiss.IndexFlatL2(EMBEDDING_DIM)
        _faiss_meta = []
        print("[FAISS] Created new empty index.")


def _save_faiss():
    faiss.write_index(_faiss_index, str(FAISS_INDEX_PATH))
    FAISS_META_PATH.write_text(json.dumps(_faiss_meta, ensure_ascii=False), encoding="utf-8")


def _get_embedding(text: str) -> np.ndarray:
    response = ai.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],
    )
    return np.array(response.data[0].embedding, dtype=np.float32)


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + chunk_size]))
        i += chunk_size - overlap
    return chunks


def index_document(file_id: str, content: str):
    global _faiss_index, _faiss_meta
    remove_document_from_index(file_id)

    chunks = _chunk_text(content)
    vectors, metas = [], []

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        try:
            vec = _get_embedding(chunk)
            vectors.append(vec)
            metas.append({"file_id": file_id, "chunk_index": i, "text": chunk})
        except Exception as e:
            print(f"[FAISS] Embedding failed for chunk {i} of {file_id}: {e}")

    if vectors:
        _faiss_index.add(np.stack(vectors))
        _faiss_meta.extend(metas)
        _save_faiss()
        print(f"[FAISS] Indexed {len(vectors)} chunks for {file_id}.")


def remove_document_from_index(file_id: str):
    global _faiss_index, _faiss_meta
    remaining = [m for m in _faiss_meta if m["file_id"] != file_id]
    if len(remaining) == len(_faiss_meta):
        return

    _faiss_index = faiss.IndexFlatL2(EMBEDDING_DIM)
    _faiss_meta = []

    if remaining:
        vectors = []
        for m in remaining:
            try:
                vectors.append(_get_embedding(m["text"]))
                _faiss_meta.append(m)
            except Exception:
                pass
        if vectors:
            _faiss_index.add(np.stack(vectors))

    _save_faiss()
    print(f"[FAISS] Removed chunks for {file_id}, index now has {_faiss_index.ntotal} vectors.")


def search_index(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    if _faiss_index is None or _faiss_index.ntotal == 0:
        return []

    query_vec = _get_embedding(query)
    k = min(top_k, _faiss_index.ntotal)
    distances, indices = _faiss_index.search(np.array([query_vec], dtype=np.float32), k)

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx == -1:
            continue
        meta = _faiss_meta[idx].copy()
        meta["score"] = float(dist)
        results.append(meta)
    return results


def get_admin_faiss_stats():
    total_vectors = _faiss_index.ntotal if _faiss_index else 0
    file_ids = list({m["file_id"] for m in _faiss_meta})
    return {"total_vectors": total_vectors, "total_documents": len(file_ids), "indexed_file_ids": file_ids}


def rebuild_admin_faiss():
    global _faiss_index, _faiss_meta
    _faiss_index = faiss.IndexFlatL2(EMBEDDING_DIM)
    _faiss_meta = []
    _save_faiss()

    indexed = 0
    for path in STORAGE_DIR.glob("*.md"):
        file_id = path.stem
        content = path.read_text(encoding="utf-8")
        index_document(file_id, content)
        indexed += 1

    return {"message": f"Rebuilt index for {indexed} documents.", "total_vectors": _faiss_index.ntotal}


def rag_query(query: str, top_k: int = 5) -> dict:
    chunks = search_index(query, top_k=top_k)
    if not chunks:
        return {
            "answer": "No documents have been indexed yet. Please upload or scrape some documents first.",
            "sources": [], "chunks_used": [],
        }
    context = "\n\n---\n\n".join(c["text"] for c in chunks)
    response = ai.chat.completions.create(
        model="gpt-4o", max_tokens=1500,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Answer the user's question using ONLY the provided context. If the answer is not in the context, say so clearly."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ],
    )
    return {"answer": response.choices[0].message.content.strip()}


# ═══════════════════════════════════════════════════════════════════════════════
#  STORAGE HELPERS  (markdown files on disk)
# ═══════════════════════════════════════════════════════════════════════════════

def save_file(file_id: str, content: str) -> Path:
    path = STORAGE_DIR / f"{file_id}.md"
    path.write_text(content, encoding="utf-8")
    return path


def load_file(file_id: str) -> str:
    path = STORAGE_DIR / f"{file_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"File {file_id} not found")
    return path.read_text(encoding="utf-8")


def save_meta(file_id: str, meta: dict):
    (STORAGE_DIR / f"{file_id}.meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def load_meta(file_id: str) -> dict:
    path = STORAGE_DIR / f"{file_id}.meta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_json(file_id: str, data: dict) -> Path:
    path = STORAGE_DIR / f"{file_id}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def make_file_id(filename: str) -> str:
    stem = Path(filename).stem
    safe = re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9_\-]", "_", stem)).strip("_")
    candidate, counter = safe, 2
    while (STORAGE_DIR / f"{candidate}.md").exists():
        candidate = f"{safe}_{counter}"
        counter += 1
    return candidate


# ═══════════════════════════════════════════════════════════════════════════════
#  HTML → MARKDOWN
# ═══════════════════════════════════════════════════════════════════════════════

def html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    lines = []
    for elem in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "blockquote"]):
        tag = elem.name
        text = elem.get_text(separator=" ", strip=True)
        if not text:
            continue
        if tag == "h1":           lines.append(f"# {text}")
        elif tag == "h2":         lines.append(f"## {text}")
        elif tag == "h3":         lines.append(f"### {text}")
        elif tag == "h4":         lines.append(f"#### {text}")
        elif tag == "li":         lines.append(f"- {text}")
        elif tag == "pre":        lines.append(f"```\n{text}\n```")
        elif tag == "blockquote": lines.append(f"> {text}")
        else:                     lines.append(text)
        lines.append("")
    return "\n".join(lines).strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  DOCLING HELPERS  (PDF / image OCR extraction)
# ═══════════════════════════════════════════════════════════════════════════════

BULLET_CHARS = ["•", "·", "●", "▪", "", "o", "◦", "-"]
CHECKBOX_CHARS = ["□", "☐", "✓", "✔", "✗", "✘", ""]


def _get_by_ref(doc: Dict[str, Any], ref_str: str) -> Any:
    if not ref_str.startswith("#/"):
        raise ValueError(f"Bad ref: {ref_str}")
    obj: Any = doc
    for p in ref_str[2:].split("/"):
        obj = obj[int(p)] if isinstance(obj, list) else obj[p]
    return obj


def _extract_pages(text_obj: Dict[str, Any]) -> set:
    pages = set()
    for prov in text_obj.get("prov", []):
        if prov.get("page_no") is not None:
            pages.add(int(prov["page_no"]))
    return pages


def _clean_bullet(s: str) -> str:
    s = (s or "").lstrip()
    if not s:
        return s
    for ch in BULLET_CHARS + CHECKBOX_CHARS:
        if s.startswith(ch):
            return s[len(ch):].lstrip()
    return re.sub(r"^[^\w\d]+", "", s).lstrip()


def _format_list_item(obj: Dict[str, Any], indent: int) -> str:
    text = (obj.get("text") or "").strip()
    orig = (obj.get("orig") or "").strip()
    marker = (obj.get("marker") or "").strip()
    pad = "    " * indent
    if obj.get("enumerated") and marker:
        return pad + f"{marker} {text}"
    base = _clean_bullet(orig) or text
    return pad + f"- {base}"


def _format_checkbox(obj: Dict[str, Any], indent: int) -> str:
    orig = (obj.get("orig") or "").strip()
    text = (obj.get("text") or "").strip()
    pad = "    " * indent
    base = _clean_bullet(orig) or _clean_bullet(text) or text
    label = obj.get("label") or ""
    box = "[x]" if "selected" in label else "[ ]"
    return f"{pad}{box} {base}"


def _docling_doc_to_markdown(doc_dict: Dict[str, Any]) -> str:
    lines: List[str] = []

    def _render_table(table_obj):
        grid = table_obj.get("grid") or table_obj.get("data", {}).get("grid", [])
        if not grid:
            return []
        all_texts = [(cell.get("text") or "").strip() for row in grid for cell in row]
        is_menu = any(re.match(r'^\$\d+', t) for t in all_texts)

        if is_menu:
            tlines, seen = [], set()
            for row in grid:
                unique_cells = []
                for cell in row:
                    t = (cell.get("text") or "").strip()
                    if t and t not in seen:
                        seen.add(t)
                        unique_cells.append(t)
                if not unique_cells:
                    continue
                price = next((t for t in unique_cells if re.match(r'^\$\d+', t)), None)
                content_cells = [t for t in unique_cells if not re.match(r'^\$\d+', t)]
                content = " | ".join(content_cells) if content_cells else ""
                if content and price:
                    tlines.append(f"- {content} {price}")
                elif content:
                    tlines.append(f"- {content}")
            return tlines

        tlines = []
        for row_idx, row in enumerate(grid):
            cells = [str((cell.get("text") or "").strip()) for cell in row]
            tlines.append("| " + " | ".join(cells) + " |")
            if row_idx == 0:
                tlines.append("| " + " | ".join(["---"] * len(cells)) + " |")
        return tlines

    def walk_ref(ref: str, indent: int = 0):
        kind = ref.split("/")[1]
        try:
            obj = _get_by_ref(doc_dict, ref)
        except Exception:
            return

        if kind == "texts":
            if obj.get("content_layer") != "body":
                return
            label = obj.get("label", "")
            text = (obj.get("text") or "").strip()
            if not text:
                return
            if label == "section_header":
                lines.append(f"\n{'#' * obj.get('level', 2)} {text}\n")
            elif label == "list_item":
                lines.append(_format_list_item(obj, indent))
            elif label and label.startswith("checkbox"):
                lines.append(_format_checkbox(obj, indent))
            else:
                lines.append(text)

        elif kind == "groups":
            child_indent = indent + 1 if obj.get("label") == "list" else indent
            for child in obj.get("children", []):
                walk_ref(child["$ref"], child_indent)

        elif kind == "tables":
            tlines = _render_table(obj)
            if tlines:
                lines.append("")
                lines.extend(tlines)
                lines.append("")

        elif kind == "pictures":
            captions, ocr_texts = [], []
            for ch in obj.get("children", []):
                try:
                    t = _get_by_ref(doc_dict, ch["$ref"])
                    text = (t.get("text") or "").strip()
                    label = (t.get("label") or "").strip()
                    if not text:
                        continue
                    (captions if label in ("caption", "footnote") else ocr_texts).append(text)
                except Exception:
                    pass
            parts = []
            if captions:  parts.append("Caption: " + " ".join(captions))
            if ocr_texts: parts.append("Image text: " + " ".join(ocr_texts))
            if parts:
                lines.append(f"*[Image — {' | '.join(parts)}]*")

    for child in doc_dict.get("body", {}).get("children", []):
        walk_ref(child["$ref"], indent=0)
        lines.append("")

    return "\n".join(lines).strip()


def _docling_doc_to_structured_json(doc_dict: Dict[str, Any], file_id: str, filename: str) -> Dict[str, Any]:
    blocks: List[Dict[str, Any]] = []

    def walk_ref(ref: str, current_section: Optional[str] = None):
        kind = ref.split("/")[1]
        try:
            obj = _get_by_ref(doc_dict, ref)
        except Exception:
            return
        pages = sorted(_extract_pages(obj))

        if kind == "texts":
            if obj.get("content_layer") != "body":
                return
            text = (obj.get("text") or "").strip()
            if not text:
                return
            blocks.append({"type": obj.get("label", "paragraph"), "text": text, "section": current_section, "pages": pages})

        elif kind == "groups":
            items, g_pages = [], set()
            for ch in obj.get("children", []):
                try:
                    t = _get_by_ref(doc_dict, ch["$ref"])
                    text = (t.get("text") or "").strip()
                    if text:
                        items.append(text)
                        g_pages.update(_extract_pages(t))
                except Exception:
                    pass
            if items:
                blocks.append({"type": obj.get("label", "group"), "items": items, "section": current_section, "pages": sorted(g_pages)})

        elif kind == "tables":
            grid = obj.get("grid", [])
            rows = [[str((c.get("text") or "").strip()) for c in row] for row in grid]
            if rows:
                blocks.append({"type": "table", "headers": rows[0], "rows": rows[1:], "section": current_section, "pages": pages})

        elif kind == "pictures":
            captions, ocr_texts, p_pages = [], [], set(pages)
            for ch in obj.get("children", []):
                try:
                    t = _get_by_ref(doc_dict, ch["$ref"])
                    text = (t.get("text") or "").strip()
                    label = (t.get("label") or "").strip()
                    if not text:
                        continue
                    p_pages.update(_extract_pages(t))
                    (captions if label in ("caption", "footnote") else ocr_texts).append(text)
                except Exception:
                    pass
            if captions or ocr_texts:
                blocks.append({"type": "picture", "captions": captions, "ocr_text": ocr_texts, "section": current_section, "pages": sorted(p_pages)})

    current_section = None
    for child in doc_dict.get("body", {}).get("children", []):
        ref = child["$ref"]
        if ref.split("/")[1] == "texts":
            try:
                obj = _get_by_ref(doc_dict, ref)
                if obj.get("label") == "section_header":
                    current_section = (obj.get("text") or "").strip()
            except Exception:
                pass
        walk_ref(ref, current_section)

    origin = doc_dict.get("origin", {})
    return {
        "file_id": file_id, "filename": filename,
        "page_count": len(doc_dict.get("pages", {})),
        "extracted_at": datetime.utcnow().isoformat() + "Z",
        "source": {"mime_type": origin.get("mimetype"), "original_filename": origin.get("filename")},
        "blocks": blocks,
    }


def image_to_docling(img_path: Path, file_id: str, filename: str):
    print(f"[Docling] Starting image OCR extraction for {file_id}...")
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.ocr_options = EasyOcrOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.images_scale = 2.0

    converter = DocumentConverter(
        format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options)}
    )
    result = converter.convert(str(img_path))
    doc_dict = result.document.export_to_dict()
    print(f"[Docling] Image extraction complete for {file_id}.")

    markdown = _docling_doc_to_markdown(doc_dict)
    structured_json = _docling_doc_to_structured_json(doc_dict, file_id, filename)
    structured_json["docling_raw"] = doc_dict
    return markdown, structured_json


def pdf_to_docling(pdf_path: Path, file_id: str, filename: str):
    print(f"[Docling] Starting full OCR extraction for {file_id}...")
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.ocr_options = EasyOcrOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.images_scale = 2.0
    pipeline_options.generate_picture_images = True

    converter = DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=pipeline_options)}
    )
    result = converter.convert(str(pdf_path))
    doc_dict = result.document.export_to_dict()
    print(f"[Docling] Extraction complete for {file_id}.")

    markdown = _docling_doc_to_markdown(doc_dict)
    structured_json = _docling_doc_to_structured_json(doc_dict, file_id, filename)
    structured_json["docling_raw"] = doc_dict
    return markdown, structured_json


# ═══════════════════════════════════════════════════════════════════════════════
#  KB EXPORT  (database → text files for LlamaIndex)
# ═══════════════════════════════════════════════════════════════════════════════

def get_last_file_index_and_size():
    if not os.path.exists(SAVE_PATH):
        os.makedirs(SAVE_PATH)
        return 1, 0
    files = [f for f in os.listdir(SAVE_PATH) if re.match(rf"{BASE_FILE_NAME}(\d+)\.txt", f)]
    if not files:
        return 1, 0
    files.sort(key=lambda x: int(re.findall(rf"{BASE_FILE_NAME}(\d+)\.txt", x)[0]))
    last_file = files[-1]
    last_index = int(re.findall(rf"{BASE_FILE_NAME}(\d+)\.txt", last_file)[0])
    size = os.path.getsize(os.path.join(SAVE_PATH, last_file))
    return last_index, size


def export_qa_pairs_job():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT ChatHistoryID, question, answer, status, suggestedanswer "
        "FROM CDPChatHistory WHERE IsKBUpdated = 1 AND PublishStatus = 'ReadyToPublish'"
    )
    rows = cursor.fetchall()
    if not rows:
        conn.close()
        return {"status": "ok", "message": "No new records to export", "files": []}

    file_index, last_file_size = get_last_file_index_and_size()
    current_file_path = os.path.join(SAVE_PATH, f"{BASE_FILE_NAME}{file_index}.txt")
    mode = 'a' if last_file_size < MAX_FILE_SIZE else 'w'
    if mode == 'w':
        file_index += 1
        current_file_path = os.path.join(SAVE_PATH, f"{BASE_FILE_NAME}{file_index}.txt")

    current_file = open(current_file_path, mode, encoding='utf-8')
    created_files = {os.path.basename(current_file_path)}

    for row in rows:
        chat_id = row[0]
        print(f"Processing ChatHistoryID: {chat_id}")
        question = row[1] or ''
        answer = clean_text(row[2])
        suggested = clean_text(row[4])
        status = (row[3] or '').strip()

        if status == 'PartiallyCorrect':
            info = f"{answer.strip()} {suggested.strip()}"
        elif status == 'InCorrect':
            info = suggested.strip()
        else:
            continue

        pair_text = f"Title: {question.strip()}\nInformation: {info}\n\n"

        if current_file.tell() + len(pair_text.encode('utf-8')) > MAX_FILE_SIZE:
            current_file.close()
            file_index += 1
            current_file_path = os.path.join(SAVE_PATH, f"{BASE_FILE_NAME}{file_index}.txt")
            current_file = open(current_file_path, 'w', encoding='utf-8')
            created_files.add(os.path.basename(current_file_path))

        current_file.write(pair_text)
        cursor.execute(
            "UPDATE CDPChatHistory SET IsKBUpdated = 0, PublishStatus = 'Published' WHERE ChatHistoryID = ?",
            chat_id,
        )
    conn.commit()
    current_file.close()
    conn.close()
    return {"status": "ok", "files": sorted(list(created_files))}


# ═══════════════════════════════════════════════════════════════════════════════
#  LLAMAINDEX CHATBOT ENGINE  (FAISS + text-embedding-3-large, 3072-dim)
# ═══════════════════════════════════════════════════════════════════════════════

openai_llm = LlamaOpenAI(
    api_key=OPENAI_API_KEY,
    model_name="gpt-3.5-turbo",
    temperature=0.1,
    top_p=0.8,
    max_tokens=1024,
)

# Global query engine — loaded on startup, rebuilt via /update-index
query_engine = None


def load_chatbot_index():
    """Load existing LlamaIndex FAISS index from disk (called at startup)."""
    global query_engine
    persist_dir = "./storage"
    try:
        vector_store = FaissVectorStore.from_persist_dir(persist_dir)
        storage_context = StorageContext.from_defaults(vector_store=vector_store, persist_dir=persist_dir)
        index = load_index_from_storage(storage_context=storage_context)
        query_engine = index.as_query_engine(llm=openai_llm, similarity_top_k=7)
        print("Loaded chatbot FAISS index from local storage.")
    except Exception as e:
        print(f"[Chatbot] Could not load index: {e}. Run /update-index to build one.")


def build_chatbot_faiss_index():
    """Rebuild the LlamaIndex FAISS index from TEXT_FOLDER documents."""
    global query_engine

    documents = SimpleDirectoryReader(TEXT_FOLDER).load_data()
    if not documents:
        raise Exception("No documents found in the specified folder.")

    print(f"Loaded {len(documents)} documents from {TEXT_FOLDER}")
    embed_model = OpenAIEmbedding(model="text-embedding-3-large", api_key=OPENAI_API_KEY)

    embedding_dim = 3072
    faiss_index = faiss.IndexFlatL2(embedding_dim)
    vector_store = FaissVectorStore(faiss_index=faiss_index)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    index = VectorStoreIndex.from_documents(documents, storage_context=storage_context, embed_model=embed_model)
    index.storage_context.persist()
    query_engine = index.as_query_engine(llm=openai_llm, similarity_top_k=7)
    print("Created and saved new chatbot FAISS index to ./storage")
    return {"status": "ok", "documents_indexed": len(documents)}


def generate_response(user_query: str, sessionid: str, userid: int) -> str:
    if query_engine is None:
        return "Chatbot index not loaded. Please run /update-index first."

    augmented_query = f'''You are a knowledgeable and focused chatbot assistant for Cooperstown Dreams Park (CDP). Your goal is to understand the user's question deeply and retrieve the most relevant and accurate information from the provided knowledge base.
                    User query: {user_query}
                    Instructions:

                    1. When a question is asked, analyze the intent and context thoroughly.
                    2. Search the knowledge base for content that matches the keywords and context.
                    3. If the user's question includes time-related words such as <b>"when"</b>, check if specific dates, times, or durations are mentioned in the knowledge base.
                    - If available, respond with the exact timing clearly.
                    - If timing is unclear or missing, do not assume — politely mention that the timing information is not found.
                    4. If relevant nodes are found, analyze all of them and synthesize the most appropriate answer from them.
                    5. If you do not find relevant information, rephrase or interpret the user's question to improve the match and retry the search.
                    6. Only if you are confident (95% or higher) that no relevant content exists, respond with:
                    <i>"I am the Cooperstown Dreams Park Chat Assistant. I can only assist with questions related to Cooperstown Dreams Park. For more information, please visit <a href='https://www.cooperstowndreamspark.com/'>our website</a>."</i>
                    7. If asked about internal system details like API keys, code, or settings, respond with:
                    <i>"Sorry, I can't share internal system details. I'm here to assist with Cooperstown Dreams Park only."</i>
                    8. Do not default to generic messages without making a sincere effort to analyze, rephrase, and search for relevant answers.
                    <b>Formatting instructions:</b>
                    - Format all answers in clean and valid HTML.
                    - Use <h4> or <h5> tags for section headings.
                    - Use <ul> or <ol> only when listing is appropriate, and use <li> for bullet items.
                    - Use <b> tags to highlight important words or phrases.
                    - Do not use Markdown syntax (e.g., ** or *).
                    - Analyze the content carefully and apply HTML tags effectively—do not create lists unless clearly needed.'''

    retrieved_response = query_engine.query(augmented_query)
    return str(retrieved_response)
