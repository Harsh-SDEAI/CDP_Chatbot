"""
Unified FastAPI application — merges Admin Content Manager + CDP Chatbot APIs.
All routes from both services are served on a single port.
"""
import json
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import STORAGE_DIR, IMAGES_DIR, get_db_connection
from services import (
    # Admin FAISS
    load_admin_faiss, index_document, remove_document_from_index,
    search_index, get_admin_faiss_stats, rebuild_admin_faiss, rag_query,
    # Storage
    save_file, load_file, save_meta, load_meta, save_json, make_file_id,
    # Document processing
    html_to_markdown, pdf_to_docling, image_to_docling,
    # KB export
    export_qa_pairs_job,
    # Chatbot
    load_chatbot_index, build_chatbot_faiss_index, generate_response,
)

# ── App Setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="CDP Unified API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")


# ── Request Models ────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    url: str

class SaveContentRequest(BaseModel):
    file_id: str
    content: str

class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = 5

class ChatRequest(BaseModel):
    query: str
    userid: int
    sessionid: str


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    load_admin_faiss()
    load_chatbot_index()


# ═══════════════════════════════════════════════════════════════════════════════
#  GENERAL
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"message": "CDP Unified API is running"}


# ═══════════════════════════════════════════════════════════════════════════════
#  CONTENT MANAGEMENT  (was Admin API)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/scrape")
async def scrape_url(body: ScrapeRequest):
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.get(
                body.url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AdminContentBot/1.0)"},
            )
            response.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

    markdown = html_to_markdown(response.text)
    file_id = str(uuid.uuid4())

    save_file(file_id, markdown)
    save_meta(file_id, {
        "type": "scraped",
        "url": body.url,
        "filename": f"{body.url.split('//')[-1].split('/')[0]}_{file_id[:8]}.md",
        "created_at": datetime.utcnow().isoformat() + "Z",
    })
    index_document(file_id, markdown)

    return {"file_id": file_id, "content": markdown, "url": body.url, "source_url": body.url}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    filename = file.filename
    ext = Path(filename).suffix.lower()
    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
    ALLOWED_EXTS = {".pdf", ".txt", ".md"} | IMAGE_EXTS

    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    raw_content = await file.read()
    file_id = make_file_id(filename)

    if ext == ".pdf":
        tmp_pdf = STORAGE_DIR / f"{file_id}_tmp.pdf"
        tmp_pdf.write_bytes(raw_content)
        try:
            markdown, structured_json = pdf_to_docling(tmp_pdf, file_id, filename)
        finally:
            tmp_pdf.unlink(missing_ok=True)
        save_file(file_id, markdown)
        json_path = save_json(file_id, structured_json)
        content = markdown
        extra = {"json_path": str(json_path), "page_count": structured_json.get("page_count", 0), "block_count": len(structured_json.get("blocks", []))}

    elif ext in IMAGE_EXTS:
        tmp_img = STORAGE_DIR / f"{file_id}_tmp{ext}"
        tmp_img.write_bytes(raw_content)
        try:
            markdown, structured_json = image_to_docling(tmp_img, file_id, filename)
        finally:
            tmp_img.unlink(missing_ok=True)
        save_file(file_id, markdown)
        json_path = save_json(file_id, structured_json)
        content = markdown
        extra = {"json_path": str(json_path), "page_count": 1, "block_count": len(structured_json.get("blocks", []))}

    else:
        content = raw_content.decode("utf-8", errors="replace").strip()
        save_file(file_id, content)
        extra = {}

    save_meta(file_id, {"type": "uploaded", "filename": filename, "url": None, "created_at": datetime.utcnow().isoformat() + "Z", **extra})
    index_document(file_id, content)

    return {"file_id": file_id, "content": content, "filename": filename, "original_filename": filename, "sizeBytes": len(raw_content), **extra}


@app.get("/content/{file_id}")
def get_content(file_id: str):
    try:
        content = load_file(file_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    meta = load_meta(file_id)
    return {"file_id": file_id, "content": content, "type": meta.get("type", "unknown"), "filename": meta.get("filename", f"{file_id}.md"), "url": meta.get("url")}


@app.get("/content/{file_id}/json")
def get_json_content(file_id: str):
    json_path = STORAGE_DIR / f"{file_id}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="JSON extraction not found for this file.")
    return json.loads(json_path.read_text(encoding="utf-8"))


@app.put("/content")
def save_content(body: SaveContentRequest):
    try:
        load_file(body.file_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    save_file(body.file_id, body.content)
    index_document(body.file_id, body.content)
    return {"file_id": body.file_id, "message": "Content saved and re-indexed successfully"}


@app.get("/files")
def list_files():
    files = []
    for path in STORAGE_DIR.glob("*.md"):
        file_id = path.stem
        meta = load_meta(file_id)
        files.append({
            "file_id": file_id,
            "filename": meta.get("filename", f"{file_id}.md"),
            "type": meta.get("type", "scraped"),
            "url": meta.get("url"),
            "size_bytes": path.stat().st_size,
            "last_modified": path.stat().st_mtime,
            "has_json": (STORAGE_DIR / f"{file_id}.json").exists(),
            "page_count": meta.get("page_count"),
            "block_count": meta.get("block_count"),
        })
    files.sort(key=lambda f: f["last_modified"], reverse=True)
    return {"files": files}


@app.delete("/content/{file_id}")
def delete_content(file_id: str):
    md_path = STORAGE_DIR / f"{file_id}.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    md_path.unlink()

    for p in [STORAGE_DIR / f"{file_id}.meta.json", STORAGE_DIR / f"{file_id}.json"]:
        if p.exists():
            p.unlink()

    img_dir = IMAGES_DIR / file_id
    if img_dir.exists():
        shutil.rmtree(img_dir)

    remove_document_from_index(file_id)
    return {"file_id": file_id, "message": "Deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════════
#  ADMIN RAG  (was /rag/* routes)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/rag/query")
def rag_query_endpoint(body: RAGQueryRequest):
    return rag_query(body.query, body.top_k)


@app.get("/rag/index/stats")
def rag_index_stats():
    return get_admin_faiss_stats()


@app.post("/rag/index/rebuild")
def rag_rebuild_index():
    return rebuild_admin_faiss()


@app.delete("/rag/index/{file_id}")
def rag_remove_from_index(file_id: str):
    remove_document_from_index(file_id)
    return {"file_id": file_id, "message": "Removed from index."}


# ═══════════════════════════════════════════════════════════════════════════════
#  CHATBOT  (was CDPGPT_Enhanced API)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/chat")
def chat(request: ChatRequest):
    start_time = time.time()
    response = generate_response(request.query, request.sessionid, request.userid)
    end_time = time.time()

    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO CDPChatHistory (SessionId, UserRegistrationId, Question, Answer) VALUES (?, ?, ?, ?)",
            (request.sessionid, request.userid, request.query, response),
        )
        db.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database insert error: {e}")
    finally:
        db.close()

    return {"response": response, "time_taken": end_time - start_time}


@app.post("/update-kb")
def update_kb():
    try:
        return export_qa_pairs_job()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/update-index")
def update_index():
    try:
        return build_chatbot_faiss_index()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build FAISS index: {str(e)}")


@app.post("/update-all")
def update_all():
    try:
        kb_response = export_qa_pairs_job()
        if kb_response.get("status") != "ok":
            raise Exception("Knowledge base export failed")

        index_response = build_chatbot_faiss_index()
        if index_response.get("status") != "ok":
            raise Exception("Index build failed")

        return {
            "status": "ok",
            "message": "Successfully exported KB and built index",
            "kb": kb_response,
            "index": index_response,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history")
def get_history():
    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT SessionId, UserRegistraionId, Question, Answer, TimeStamp "
            "FROM CDPChatHistory ORDER BY id DESC"
        )
        rows = cursor.fetchall()
        history = [
            {
                "session_id": row[0],
                "user_registration_id": row[1],
                "question": row[2],
                "answer": row[3],
                "timestamp": row[4],
            }
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {e}")
    finally:
        db.close()

    return {"conversation_history": history}


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
