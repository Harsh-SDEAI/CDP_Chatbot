from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
import re
import json
from pydantic import BaseModel
import faiss
import os
import time
import httpx
import pyodbc
import numpy as np
import openai
import settings
from fastapi.middleware.cors import CORSMiddleware

# Database Credentials
SERVER_NAME = settings.DB_SERVER
DRIVER_NAME = settings.DB_DRIVER
DATABASE_NAME = settings.DB_NAME
USER_NAME = settings.DB_USER
PASSWORD = settings.DB_PASSWORD
SAVE_PATH = settings.SAVE_PATH
MAX_FILE_SIZE = settings.MAX_FILE_SIZE  # 25 * 1024
BASE_FILE_NAME = settings.BASE_FILE_NAME
API_KEYS = os.getenv("API_KEYS", "").split(",")
app = FastAPI()
client = httpx.Client(timeout=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or set specific domains: ["http://localhost:4200"]
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST, PUT, DELETE, etc
    allow_headers=["*"],
)
# ----------------------- Database Setup -----------------------
def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API Key required")

    if x_api_key not in settings.API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    
def get_db_connection():
    return pyodbc.connect(
        'DRIVER='+DRIVER_NAME+';'
        'SERVER='+SERVER_NAME+';'
        'DATABASE='+DATABASE_NAME+';'
        'UID='+USER_NAME+';PWD='+PASSWORD+';'
    )
 
def clean_text(text):
    text = re.sub(r'<[^>]*>', '', text or '')
    text = re.sub(r'[\n\r\t]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    return text.strip()

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

    # cursor.execute("SELECT TOP 1 TableID, ChatHistoryID FROM ChatHistoryIDInfo ORDER BY 1 DESC")
    # last_processed = cursor.fetchone()
    # last_processed_id = last_processed.ChatHistoryID 
    # print(f"Last processed ChatHistoryID: {last_processed_id}")

    # cursor.execute("SELECT TOP 1 ChatHistoryID FROM cdpchathistorystatus ORDER BY ChatHistoryID DESC")
    # latest = cursor.fetchone()
    # latest_chat_history_id = latest.ChatHistoryID

    # if latest_chat_history_id > last_processed_id:
    #     cursor.execute("INSERT INTO ChatHistoryIDInfo (ChatHistoryID, CreatedOn) VALUES (?, CURRENT_TIMESTAMP)", latest_chat_history_id)
    #     conn.commit()

    # cursor.execute("SELECT question, answer, suggestedanswer, newstatus FROM cdpchathistorystatus WHERE ChatHistoryID > ?", last_processed_id)
    cursor.execute("SELECT ChatHistoryID, question, answer, status, suggestedanswer FROM CDPChatHistory WHERE IsKBUpdated = 1 AND PublishStatus = 'ReadyToPublish'")
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
    created_files = set()
    created_files.add(os.path.basename(current_file_path))

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
        cursor.execute("UPDATE CDPChatHistory SET IsKBUpdated = 0, PublishStatus = 'Published' WHERE ChatHistoryID = ?", chat_id)
    conn.commit()
    current_file.close()
    conn.close()
    return {"status": "ok", "files": sorted(list(created_files))}
# ----------------------- OpenAI Client -----------------------
openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIM = 3072
LLM_MODEL = "gpt-3.5-turbo"
PERSIST_DIR = "./storage"
FAISS_INDEX_PATH = os.path.join(PERSIST_DIR, "faiss.index")
TEXTS_PATH = os.path.join(PERSIST_DIR, "texts.json")

# ----------------------- FAISS Helpers -----------------------
def load_text_files(folder: str) -> list[str]:
    """Read all .txt files from a folder, one string per file."""
    texts = []
    for fname in sorted(os.listdir(folder)):
        if fname.endswith(".txt"):
            with open(os.path.join(folder, fname), "r", encoding="utf-8") as f:
                texts.append(f.read())
    return texts

def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a list of texts using OpenAI embeddings API. Handles batching."""
    all_embeddings = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        all_embeddings.extend([e.embedding for e in resp.data])
    return np.array(all_embeddings, dtype=np.float32)

def build_and_persist_index(texts: list[str]) -> tuple[faiss.Index, list[str]]:
    """Build a FAISS index from texts, persist index + texts to disk."""
    vectors = embed_texts(texts)
    idx = faiss.IndexFlatL2(EMBEDDING_DIM)
    idx.add(vectors)
    os.makedirs(PERSIST_DIR, exist_ok=True)
    faiss.write_index(idx, FAISS_INDEX_PATH)
    with open(TEXTS_PATH, "w", encoding="utf-8") as f:
        json.dump(texts, f)
    return idx, texts

def load_index_and_texts() -> tuple[faiss.Index, list[str]]:
    """Load FAISS index and texts from disk."""
    idx = faiss.read_index(FAISS_INDEX_PATH)
    with open(TEXTS_PATH, "r", encoding="utf-8") as f:
        texts = json.load(f)
    return idx, texts

def search_index(query: str, idx: faiss.Index, texts: list[str], top_k: int = 7) -> list[str]:
    """Embed query, search FAISS, return top_k text chunks."""
    q_vec = embed_texts([query])
    _, I = idx.search(q_vec, top_k)
    return [texts[i] for i in I[0] if i < len(texts)]

# ----------------------- Load or Build Index at Startup -----------------------
text_folder = settings.TEXT_FOLDER

if os.path.exists(FAISS_INDEX_PATH) and os.path.exists(TEXTS_PATH):
    faiss_index, document_texts = load_index_and_texts()
    print("Loaded FAISS index from Local machine.")
else:
    document_texts = load_text_files(text_folder)
    if not document_texts:
        raise Exception("No documents found in the specified folder.")
    print(f"Loaded {len(document_texts)} documents.")
    faiss_index, document_texts = build_and_persist_index(document_texts)
    print("Created and saved new FAISS index.")


# ----------------------- Request Model -----------------------
class ChatRequest(BaseModel):
    query: str
    userid: int
    sessionid: str

class ChatHistoryRequest(BaseModel):
    userid: int

class SessionHistoryRequest(BaseModel):
    userid: int
    sessionid: str
 
# ----------------------- Helper Function -----------------------
SYSTEM_PROMPT = “””You are a knowledgeable and focused chatbot assistant for Cooperstown Dreams Park (CDP). Your goal is to understand the user’s question deeply and provide the most relevant and accurate answer using ONLY the provided context.

Instructions:
1. When a question is asked, analyze the intent and context thoroughly.
2. Search the provided context for content that matches the keywords and meaning.
3. If the user’s question includes time-related words such as “when”, check if specific dates, times, or durations are mentioned in the context.
   - If available, respond with the exact timing clearly.
   - If timing is unclear or missing, do not assume — politely mention that the timing information is not found.
4. Analyze all provided context chunks and synthesize the most appropriate answer.
5. If you do not find relevant information in the context, respond with:
   <i>”I am the Cooperstown Dreams Park Chat Assistant. I can only assist with questions related to Cooperstown Dreams Park. For more information, please visit <a href=’https://www.cooperstowndreamspark.com/’>our website</a>.”</i>
6. If asked about internal system details like API keys, code, or settings, respond with:
   <i>”Sorry, I can’t share internal system details. I’m here to assist with Cooperstown Dreams Park only.”</i>
7. Do not default to generic messages without making a sincere effort to analyze the context.

Formatting instructions:
- Format all answers in clean and valid HTML.
- Use <h4> or <h5> tags for section headings.
- Use <ul> or <ol> only when listing is appropriate, and use <li> for bullet items.
- Use <b> tags to highlight important words or phrases.
- Do not use Markdown syntax (e.g., ** or *).
- Analyze the content carefully and apply HTML tags effectively—do not create lists unless clearly needed.”””

def generate_response(user_query: str, sessionid: int, userid: int) -> str:
    # 1. Retrieve relevant chunks from FAISS
    chunks = search_index(user_query, faiss_index, document_texts, top_k=7)
    context = “\n\n---\n\n”.join(chunks)

    # 2. Send to OpenAI with context
    response = openai_client.chat.completions.create(
        model=LLM_MODEL,
        temperature=0.1,
        top_p=0.8,
        max_tokens=1024,
        messages=[
            {“role”: “system”, “content”: SYSTEM_PROMPT},
            {“role”: “user”, “content”: f”Context:\n{context}\n\nUser question: {user_query}”}
        ]
    )
    return response.choices[0].message.content

# ----------------------- API Endpoints -----------------------
@app.post("/chat")
def chat(request: ChatRequest, api_key: str = Depends(verify_api_key)): 
    start_time = time.time()
    user_query = request.query
    # setting limits as desired (e.g., universal_limit=20, user_limit=20).
    response = generate_response(user_query, request.sessionid, request.userid)
    end_time = time.time()
    # Store the conversation in SQL Server (universal_history)
    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("INSERT INTO CDPChatHistory (SessionId, UserRegistrationId, Question, Answer) VALUES (?, ?, ?, ?)", (request.sessionid, request.userid, user_query, response))
        db.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database insert error: {e}")
    finally:
        db.close()

    return {"response": response, "time_taken": end_time - start_time}

@app.post("/update-all")
def update_all(api_key: str = Depends(verify_api_key)):
    try:
        # 1️⃣ Call /update-kb (wait until it finishes)
        kb_response = export_qa_pairs_job() 
        if kb_response.get("status") != "ok": 
            raise Exception("Knowledge base export failed")

        # 2️⃣ Call /update-index (as function, not HTTP)
        index_response = build_faiss_index()
        if index_response.get("status") != "ok":
            raise Exception("Index build failed")

        return {
            "status": "ok",
            "message": "Successfully exported KB and built index",
            "kb": kb_response,
            "index": index_response
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# @app.post("/update-kb")
def update_kb():
    try:
        result = export_qa_pairs_job()  # 🔁 Synchronous – will wait for completion
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  
# @app.post("/update-kb")
# def update_kb(background_tasks: BackgroundTasks):
#     background_tasks.add_task(export_qa_pairs_job)
#     return {"status": "started", "message": "Export initiated in background"}


def build_faiss_index():
    try:
        global faiss_index, document_texts
        texts = load_text_files(settings.TEXT_FOLDER)
        if not texts:
            raise HTTPException(status_code=404, detail="No documents found in the specified folder.")

        print(f"Loaded {len(texts)} documents from {settings.TEXT_FOLDER}")
        faiss_index, document_texts = build_and_persist_index(texts)
        print("Created and saved new FAISS index to ./storage")
        print("New FAISS index is ready for queries.")
        return {"status": "ok", "documents_indexed": len(texts)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build FAISS index: {str(e)}")
    

@app.post("/ChatHistory")
def get_chat_history(request: ChatHistoryRequest, api_key: str = Depends(verify_api_key)):
    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("""
            SELECT
                ch.SessionId,
                ch.LastTimestamp,
                (
                    SELECT TOP 1 LEFT(sub.Question, 35)
                    FROM CDPChatHistory sub
                    WHERE sub.SessionId = ch.SessionId
                      AND sub.UserRegistrationId = ?
                    ORDER BY sub.id ASC
                ) AS ChatTitle
            FROM (
                SELECT SessionId, MAX(id) AS LatestId, MAX(TimeStamp) AS LastTimestamp
                FROM CDPChatHistory
                WHERE UserRegistrationId = ?
                GROUP BY SessionId
            ) ch
            ORDER BY ch.LatestId DESC
        """, (request.userid, request.userid))
        rows = cursor.fetchall()
        sessions = []
        for row in rows:
            sessions.append({
                "session_id": row[0],
                "last_activity": str(row[1]) if row[1] else None,
                "chat_title": row[2] or ""
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {e}")
    finally:
        db.close()

    return {"userid": request.userid, "sessions": sessions}


@app.post("/SessionHistory")
def get_session_history(request: SessionHistoryRequest, api_key: str = Depends(verify_api_key)):
    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("""
            SELECT Question, Answer, TimeStamp
            FROM CDPChatHistory
            WHERE UserRegistrationId = ? AND SessionId = ?
            ORDER BY id ASC
        """, (request.userid, request.sessionid))
        rows = cursor.fetchall()
        messages = []
        for row in rows:
            messages.append({
                "question": row[0],
                "answer": row[1],
                "timestamp": str(row[2]) if row[2] else None
            })
        chat_title = messages[0]["question"][:35] if messages else ""
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {e}")
    finally:
        db.close()

    return {
        "userid": request.userid,
        "session_id": request.sessionid,
        "chat_title": chat_title,
        "messages": messages
    }

