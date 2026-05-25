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

def get_cdp2000_connection():
    return pyodbc.connect(
        'DRIVER='+settings.CDP_DB_DRIVER+';'
        'SERVER='+settings.CDP_DB_SERVER+';'
        'DATABASE='+settings.CDP_DB_NAME+';'
        'UID='+settings.CDP_DB_USER+';PWD='+settings.CDP_DB_PASSWORD+';'
    )
 
def clean_text(text):
    text = re.sub(r'<[^>]*>', '', text or '')
    text = re.sub(r'[\n\r\t]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    return text.strip()

def get_conversation_history(userid: int, sessionid: str, limit: int) -> list[dict]:
    if limit == 0:
        return []
    db = get_db_connection()
    try:
        cursor = db.cursor()
        cursor.execute(
            "SELECT TOP (?) Question, Answer FROM CDPChatHistory "
            "WHERE UserRegistrationId = ? AND SessionId = ? "
            "ORDER BY ChatHistoryId DESC",
            (limit, userid, sessionid)
        )
        rows = cursor.fetchall()
        messages = []
        for row in reversed(rows):
            messages.append({"role": "user", "content": row[0]})
            messages.append({"role": "assistant", "content": clean_text(row[1])})
        return messages
    except Exception as e:
        print(f"[history] Error fetching conversation history: {e}")
        return []
    finally:
        db.close()

TOURNAMENT_DAY_GUIDE = """TOURNAMENT DAY GUIDE:
- Day 1: Skills competition
- Day 2: 1 regular game per team
- Days 3-4: 2 regular games per team
- Days 5-6: Bracket play, championship game on Day 6
- Day 7: Departure"""

PLAYER_CONTEXT_INSTRUCTIONS = """INSTRUCTIONS FOR USING PLAYER CONTEXT:
- For any question about the user, their team, schedule, scores, or standings, answer ONLY from the data above. Do not infer, guess, or use outside knowledge.
- When the user asks about games on a specific day, list ONLY the games shown in SCHEDULE for that day. If no games are shown for that day, say they have no games on that day. Do NOT explain why (do not mention elimination, byes, or bracket status).
- Greet the user by first name ONLY on the first message of a session (when there is no prior conversation history). Otherwise answer without a greeting.
- The TOURNAMENT DAY GUIDE is for general "what happens on day X" questions only. The player's actual SCHEDULE always takes precedence over the guide."""

def _format_game_line(game: dict, my_team_key) -> str:
    is_home = (game["HomeTeamKey"] == my_team_key)
    my_team = game["HomeTeamName"] if is_home else game["VisitorTeamName"]
    opp_team = game["VisitorTeamName"] if is_home else game["HomeTeamName"]
    my_score = game["HomeScore"] if is_home else game["VisitorScore"]
    opp_score = game["VisitorScore"] if is_home else game["HomeScore"]

    if my_score is not None and opp_score is not None:
        if my_score > opp_score:
            outcome = f"Won {my_score}-{opp_score}"
        elif my_score < opp_score:
            outcome = f"Lost {my_score}-{opp_score}"
        else:
            outcome = f"Tied {my_score}-{opp_score}"
    else:
        outcome = "Upcoming"

    game_type = game.get("GameType") or "Unknown"
    if game_type == "Schedule":
        game_type = "Regular"

    return (
        f"- Day {game['Day']} ({game['DayOfWeek']}) {game['TimeOfDay']}, "
        f"Field {game['Field']} [{game_type}]: {my_team} vs {opp_team} — {outcome}"
    )

def get_player_context(userid: int) -> str | None:
    """Fetch the player's identity, schedule, and standings and format them
    as a system-prompt context block. Returns None if the user isn't found
    or any DB call fails — caller falls back to the standard RAG flow.
    """
    db = None
    try:
        db = get_cdp2000_connection()
        cursor = db.cursor()

        cursor.execute(
            "SELECT FirstName, LastName, TeamKey FROM Roster WHERE RosterID = ?",
            (userid,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        first_name = (row[0] or "").strip().title()
        last_name = (row[1] or "").strip().title()
        team_key = row[2]
        if not team_key:
            return None

        cursor.execute(
            "SELECT Day, DayOfWeek, TimeOfDay, Field, "
            "HomeTeamName, VisitorTeamName, HomeScore, VisitorScore, HomeTeamKey, GameType "
            "FROM WSA.AllGamesCurrentYear "
            "WHERE HomeTeamKey = ? OR VisitorTeamKey = ? "
            "ORDER BY GameDateTimeField",
            (team_key, team_key)
        )
        game_rows = cursor.fetchall()

        games = []
        my_team_name = None
        for g in game_rows:
            game = {
                "Day": g[0],
                "DayOfWeek": g[1],
                "TimeOfDay": g[2],
                "Field": g[3],
                "HomeTeamName": g[4],
                "VisitorTeamName": g[5],
                "HomeScore": g[6],
                "VisitorScore": g[7],
                "HomeTeamKey": g[8],
                "GameType": g[9],
            }
            games.append(game)
            if my_team_name is None:
                is_home = (game["HomeTeamKey"] == team_key)
                my_team_name = game["HomeTeamName"] if is_home else game["VisitorTeamName"]

        cursor.execute(
            "SELECT TeamSequence, Wins, Losses, RunsFor, RunsAgainst "
            "FROM RegularCurrentStandings WHERE TeamKey = ?",
            (team_key,)
        )
        standings_row = cursor.fetchone()

        lines = ["=== PLAYER CONTEXT ===", ""]
        full_name = f"{first_name} {last_name}".strip()
        lines.append(f"Player: {full_name}" if full_name else "Player: (name not on file)")
        if my_team_name:
            lines.append(f"Team: {my_team_name}")
        lines.append("")

        if games:
            lines.append("SCHEDULE:")
            for game in games:
                lines.append(_format_game_line(game, team_key))
            lines.append("")

        if standings_row:
            seq, wins, losses, rf, ra = standings_row
            lines.append("STANDINGS (regular play):")
            lines.append(f"Standing: {seq} | Record: {wins}-{losses} | Runs: {rf}-{ra}")
            lines.append("")

        lines.append(TOURNAMENT_DAY_GUIDE)
        lines.append("")
        lines.append(PLAYER_CONTEXT_INSTRUCTIONS)
        lines.append("")
        lines.append("=== END PLAYER CONTEXT ===")

        return "\n".join(lines)

    except Exception as e:
        print(f"[player_context] Error: {e}")
        return None
    finally:
        if db is not None:
            db.close()

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
LLM_MODEL = "gpt-5-mini"
PERSIST_DIR = "./storage"
FAISS_INDEX_PATH = os.path.join(PERSIST_DIR, "faiss.index")
TEXTS_PATH = os.path.join(PERSIST_DIR, "texts.json")

# ----------------------- FAISS Helpers -----------------------
CHUNK_SIZE = 400    # characters per chunk (~200 tokens)
CHUNK_OVERLAP = 100 # overlap between consecutive chunks
MIN_CHUNK_SIZE = 200  # below this, keep merging with the next paragraph

def normalize_source_text(text: str) -> str:
    """Clean up raw source text before chunking.

    Strips ruler lines (e.g. long runs of underscores/dashes), collapses
    excessive blank lines, and trims trailing whitespace on each line.
    """
    # Drop ruler lines made of _, -, =, * (5 or more in a row, possibly with spaces).
    text = re.sub(r'(?m)^[\s]*[_\-=*]{5,}[\s]*$', '', text)
    # Trim trailing whitespace on every line.
    text = re.sub(r'[ \t]+\n', '\n', text)
    # Collapse 3+ consecutive newlines down to exactly two (paragraph break).
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into chunks aligned to Q&A pair boundaries when possible.

    Q&A pairs written by export_qa_pairs_job are separated by blank lines
    (``\\n\\n``). We split on those first so one chunk == one pair whenever
    the pair fits within chunk_size. Oversized pairs fall back to
    sentence-aware splitting with overlap.
    """
    text = normalize_source_text(text)
    if not text:
        return []

    # Split on blank lines — these are the natural Q&A pair boundaries.
    pairs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]

    chunks = []
    current_chunk = []
    current_size = 0

    for pair in pairs:
        pair_size = len(pair)

        # Oversized pair: if a short stub is buffered, prepend it to this
        # pair so the stub rides along into the first split chunk instead of
        # being emitted as an orphan. Otherwise flush the buffer first.
        if pair_size > chunk_size:
            if current_chunk and current_size < MIN_CHUNK_SIZE:
                pair = "\n\n".join(current_chunk) + "\n\n" + pair
                current_chunk = []
                current_size = 0
            elif current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_size = 0
            chunks.extend(_split_oversized(pair, chunk_size, overlap))
            continue

        # If adding this pair would overflow the current chunk, flush first —
        # BUT only if the current buffer already has enough content to stand
        # alone. Short stubs (titles, stray fragments) keep accumulating so
        # they don't get emitted as orphan chunks with no real content.
        if (current_size + pair_size > chunk_size
                and current_chunk
                and current_size >= MIN_CHUNK_SIZE):
            chunks.append("\n\n".join(current_chunk))
            current_chunk = []
            current_size = 0

        current_chunk.append(pair)
        current_size += pair_size + 2  # +2 for the "\n\n" joiner

    if current_chunk:
        # If the final buffer is a lonely stub and we have a previous chunk,
        # glue it onto the tail of that chunk instead of emitting it alone.
        final = "\n\n".join(current_chunk)
        if len(final) < MIN_CHUNK_SIZE and chunks:
            chunks[-1] = chunks[-1] + "\n\n" + final
        else:
            chunks.append(final)

    return chunks

def _split_oversized(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Sentence-aware splitter used for pairs that exceed chunk_size."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = []
    current_size = 0

    for sentence in sentences:
        sentence_size = len(sentence)

        if sentence_size > chunk_size:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_size = 0
            step = max(1, chunk_size - overlap)
            for i in range(0, sentence_size, step):
                chunks.append(sentence[i:i + chunk_size])
            continue

        if current_size + sentence_size > chunk_size and current_chunk:
            chunks.append(" ".join(current_chunk))
            overlap_sentences = []
            overlap_size = 0
            for s in reversed(current_chunk):
                if overlap_size + len(s) > overlap:
                    break
                overlap_sentences.insert(0, s)
                overlap_size += len(s) + 1
            current_chunk = overlap_sentences
            current_size = overlap_size

        current_chunk.append(sentence)
        current_size += sentence_size + 1

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks

def load_text_files(folder: str) -> list[str]:
    """Read all .txt files from a folder, chunk them, return list of chunks."""
    texts = []
    for fname in sorted(os.listdir(folder)):
        if fname.endswith(".txt"):
            with open(os.path.join(folder, fname), "r", encoding="utf-8") as f:
                content = f.read()
            texts.extend(chunk_text(content))
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
    """Build a FAISS index from texts, persist index + texts to disk.

    Uses IndexFlatIP (inner product) with L2-normalized vectors = cosine similarity,
    which is what OpenAI embeddings are designed for.
    """
    vectors = embed_texts(texts)
    faiss.normalize_L2(vectors)  # in-place normalization
    idx = faiss.IndexFlatIP(EMBEDDING_DIM)
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

def search_index(query: str, idx: faiss.Index, texts: list[str], top_k: int = 8) -> list[str]:
    """Embed query, search FAISS, return top_k text chunks (via cosine similarity)."""
    print(query)
    query = query.lower().strip()
    print(query)
    q_vec = embed_texts([query])
    faiss.normalize_L2(q_vec)  # must normalize query vector too for cosine similarity
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
    file_count = len([f for f in os.listdir(text_folder) if f.endswith(".txt")])
    print(f"Loaded {file_count} files, {len(document_texts)} chunks.")
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
SYSTEM_PROMPT = """You are a knowledgeable and focused chatbot assistant for Cooperstown Dreams Park (CDP). Your goal is to understand the user’s question deeply and provide the most relevant and accurate answer using ONLY the provided context.

Instructions:
1. When a question is asked, analyze the intent and context thoroughly.
2. Search the provided context for content that matches the keywords and meaning.
3. If the user’s question includes time-related words such as "when", check if specific dates, times, or durations are mentioned in the context.
   - If available, respond with the exact timing clearly.
   - If timing is unclear or missing, do not assume — politely mention that the timing information is not found.
4. Analyze all provided context chunks and synthesize the most appropriate answer.
5. If you do not find relevant information in the context, respond with:
   <i>"I am the Cooperstown Dreams Park Chat Assistant. I can only assist with questions related to Cooperstown Dreams Park. For more information, please visit <a href=’https://www.cooperstowndreamspark.com/’>our website</a>."</i>
6. If asked about internal system details like API keys, code, or settings, respond with:
   <i>"Sorry, I can’t share internal system details. I’m here to assist with Cooperstown Dreams Park only."</i>
7. Do not default to generic messages without making a sincere effort to analyze the context.

Formatting instructions:
- Format all answers in clean and valid HTML.
- Use <h4> or <h5> tags for section headings.
- Use <ul> or <ol> only when listing is appropriate, and use <li> for bullet items.
- Use <b> tags to highlight important words or phrases.
- Do not use Markdown syntax (e.g., ** or *).
- Analyze the content carefully and apply HTML tags effectively—do not create lists unless clearly needed."""

def generate_response(user_query: str, sessionid: str, userid: int) -> str:
    # 1. Retrieve relevant chunks from FAISS
    chunks = search_index(user_query, faiss_index, document_texts, top_k=8)

    # Debug: log the query and a preview of the retrieved chunks so we can
    # diagnose retrieval failures (e.g. when the bot falls back despite the
    # answer being in the corpus).
    print(f"[retrieval] query={user_query!r}")
    for i, c in enumerate(chunks):
        preview = c[:150].replace("\n", " ")
        print(f"  [{i}] len={len(c)} | {preview!r}")

    context = "\n\n---\n\n".join(chunks)

    # 2. Fetch prior turns from this session for follow-up question support
    history = get_conversation_history(userid, sessionid, limit=settings.USER_LIMIT)

    # 3. Fetch the player's identity, schedule, and standings for personalization.
    # Falls back to None if the user isn't found or the DB call fails.
    player_context = get_player_context(userid)
    system_content = SYSTEM_PROMPT
    if player_context:
        system_content = player_context + "\n\n" + SYSTEM_PROMPT

    # 4. Build messages: system → prior turns → current question with context
    messages = [{"role": "system", "content": system_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": f"Context:\n{context}\n\nUser question: {user_query}"})

    response = openai_client.chat.completions.create(
        model=LLM_MODEL,
        max_completion_tokens=1024,
        messages=messages
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

        file_count = len([f for f in os.listdir(settings.TEXT_FOLDER) if f.endswith(".txt")])
        print(f"Loaded {file_count} files, {len(texts)} chunks from {settings.TEXT_FOLDER}")
        faiss_index, document_texts = build_and_persist_index(texts)
        print("New FAISS index is ready for queries.")
        return {"status": "ok", "files_loaded": file_count, "chunks_indexed": len(texts)}

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
                ch.LastCreatedOn,
                (
                    SELECT TOP 1 LEFT(sub.Question, 35)
                    FROM CDPChatHistory sub
                    WHERE sub.SessionId = ch.SessionId
                      AND sub.UserRegistrationId = ?
                    ORDER BY sub.ChatHistoryId ASC
                ) AS ChatTitle
            FROM (
                SELECT SessionId, MAX(ChatHistoryId) AS LatestId, MAX(CreatedOn) AS LastCreatedOn
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
            SELECT Question, Answer, CreatedOn
            FROM CDPChatHistory
            WHERE UserRegistrationId = ? AND SessionId = ?
            ORDER BY ChatHistoryId ASC
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

