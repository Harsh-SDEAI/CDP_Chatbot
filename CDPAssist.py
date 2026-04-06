from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
import re
from pydantic import BaseModel
import faiss
import os
import time
import httpx
import pyodbc
import numpy as np
import settings
from fastapi.middleware.cors import CORSMiddleware

# LlamaIndex imports (adjust these if your package structure differs)
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, load_index_from_storage, Settings
from llama_index.vector_stores.faiss import FaissVectorStore
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.node_parser import SentenceSplitter

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
# ----------------------- Document and FAISS Setup -----------------------
# Load documents from a directory (update path as needed)
text_folder = settings.TEXT_FOLDER

# Initialize embedding model



# Set up FAISS index and LlamaIndex

# vector_store_path = os.path.join(persist_dir, "faiss.index")
# Build the index from documents 
# def load_faiss_index(persist_dir: str = "./storage"):
#     if not os.path.exists(persist_dir):
#         raise FileNotFoundError(f"Persist directory '{persist_dir}' does not exist.")

#     vector_store = FaissVectorStore.from_persist_dir(persist_dir)
#     storage_context = StorageContext.from_defaults(vector_store=vector_store, persist_dir=persist_dir)
#     index = load_index_from_storage(storage_context=storage_context)
#     print("Loaded FAISS index from local storage.")
#     return index

# if os.path.exists(persist_dir):
#     vector_store = FaissVectorStore.from_persist_dir("./storage")
#     storage_context = StorageContext.from_defaults(vector_store=vector_store, persist_dir=persist_dir)
#     index = load_index_from_storage(storage_context=storage_context)
#     print("Loaded FAISS index from Local machine.")
# else: 
#     documents = SimpleDirectoryReader(text_folder).load_data()
#     if not documents: 
#         raise Exception("No documents found in the specified folder.")
#     print(f"Loaded {len(documents)} documents.")

#     # Use if want to utilize chunking mechanism
#     # chunk_size = 2000
#     # chunk_overlap = 100
#     # parser = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
#     # nodes = parser.get_nodes_from_documents(documents)

#     embedding_dim = 3072
#     faiss_index = faiss.IndexFlatL2(embedding_dim)
#     vector_store = FaissVectorStore(faiss_index=faiss_index)
#     storage_context = StorageContext.from_defaults(vector_store=vector_store)
#     index = VectorStoreIndex.from_documents(documents, storage_context=storage_context, embed_model=embed_model)
#     #index = VectorStoreIndex(nodes, storage_context=storage_context, embed_model=embed_model)
#     index.storage_context.persist()
#     print("Created and saved new FAISS index.")

 

# ----------------------- OpenAI LLM and Query Engine -----------------------
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-large", api_key=settings.OPENAI_API_KEY)
openai_llm = OpenAI(
    api_key=settings.OPENAI_API_KEY,  
    model_name="gpt-3.5-turbo",
    temperature=0.1,
    top_p=0.8,
    max_tokens=1024
)
persist_dir = "./storage"
if os.path.exists(persist_dir):
    vector_store = FaissVectorStore.from_persist_dir(persist_dir)
    storage_context = StorageContext.from_defaults(vector_store=vector_store, persist_dir=persist_dir)
    index = load_index_from_storage(storage_context=storage_context)
    print("Loaded FAISS index from Local machine.")
else:
    documents = SimpleDirectoryReader(text_folder).load_data()
    if not documents:
        raise Exception("No documents found in the specified folder.")
    print(f"Loaded {len(documents)} documents.")
    embedding_dim = 3072
    faiss_index = faiss.IndexFlatL2(embedding_dim)
    vector_store = FaissVectorStore(faiss_index=faiss_index)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(documents, storage_context=storage_context, embed_model=Settings.embed_model)
    index.storage_context.persist()
    print("Created and saved new FAISS index.")
query_engine = index.as_query_engine(llm=openai_llm, similarity_top_k=7)


# def get_user_conversation_history_from_db(user_id: int, session_id: str, limit: int = None):
#     if limit == 0:
#         return []

#     user_history = []
#     db = get_db_connection()
#     try: 
#         cursor = db.cursor()
#         query = (
#             "SELECT TOP (?) Question, Answer FROM CDPChatHistory "
#             "WHERE UserRegistrationId = ? AND SessionId = ? "
#             "ORDER BY CreatedOn DESC"
# )
#         cursor.execute(query, (limit, user_id, session_id))

#         rows = cursor.fetchall()
#         if not rows:
#             return []

#         # Reverse to get ascending chronological order
#         for row in reversed(rows): 
#             question = row[0]
#             answer = row[1]
#             user_history.append(ChatMessage(role=MessageRole.USER, content=question))
#             user_history.append(ChatMessage(role=MessageRole.ASSISTANT, content=answer))

#     except Exception as e:
#         print("Error retrieving user conversation history:", e)
#     finally:
#         db.close()

#     return user_history


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
def generate_response(user_query: str, sessionid: int, userid: int) -> str:
    # Retrieve user-specific conversation history 
    # user_history = get_user_conversation_history_from_db(userid, sessionid, limit=settings.USER_LIMIT)  
    # formatted_history = ""
    # for msg in user_history:
    #     role = "User" if msg.role == MessageRole.USER else "Assistant"
    #     formatted_history += f"{role}: {msg.content}\n"
    user_query =f'''You are a knowledgeable and focused chatbot assistant for Cooperstown Dreams Park (CDP). Your goal is to understand the user's question deeply and retrieve the most relevant and accurate information from the provided knowledge base.
                    User query: {user_query}
                    Instructions: 

                    1. When a question is asked, analyze the intent and context thoroughly.
                    2. Search the knowledge base for content that matches the keywords and context.
                    3. If the user's question includes time-related words such as <b>“when”</b>, check if specific dates, times, or durations are mentioned in the knowledge base.  
                    - If available, respond with the exact timing clearly.  
                    - If timing is unclear or missing, do not assume — politely mention that the timing information is not found.
                    4. If relevant nodes are found, analyze all of them and synthesize the most appropriate answer from them.
                    5. If you do not find relevant information, rephrase or interpret the user’s question to improve the match and retry the search.
                    6. Only if you are confident (95% or higher) that no relevant content exists, respond with:  
                    <i>"I am the Cooperstown Dreams Park Chat Assistant. I can only assist with questions related to Cooperstown Dreams Park. For more information, please visit <a href='https://www.cooperstowndreamspark.com/'>our website</a>."</i>
                    7. If asked about internal system details like API keys, code, or settings, respond with:  
                    <i>"Sorry, I can't share internal system details. I’m here to assist with Cooperstown Dreams Park only."</i>
                    8. Do not default to generic messages without making a sincere effort to analyze, rephrase, and search for relevant answers. 
                    <b>Formatting instructions:</b>  
                    - Format all answers in clean and valid HTML.  
                    - Use <h4> or <h5> tags for section headings.  
                    - Use <ul> or <ol> only when listing is appropriate, and use <li> for bullet items.  
                    - Use <b> tags to highlight important words or phrases.  
                    - Do not use Markdown syntax (e.g., ** or *).  
                    - Analyze the content carefully and apply HTML tags effectively—do not create lists unless clearly needed.'''
    retrieved_response = query_engine.query(user_query)
    retrieved_text = str(retrieved_response)
    return retrieved_text 

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


# @app.post("/update-index")
def build_faiss_index():
    try:
        global index, query_engine
        # Load documents
        documents = SimpleDirectoryReader(settings.TEXT_FOLDER).load_data()
        if not documents:
            raise HTTPException(status_code=404, detail="No documents found in the specified folder.")
        
        print(f"Loaded {len(documents)} documents from {settings.TEXT_FOLDER}")
        embed_model = OpenAIEmbedding(model="text-embedding-3-large", api_key=settings.OPENAI_API_KEY)
        # Use if want to utilize chunking mechanism

        # chunk_size = 2000
        # chunk_overlap = 100
        # parser = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        # nodes = parser.get_nodes_from_documents(documents)

        embedding_dim = 3072
        faiss_index = faiss.IndexFlatL2(embedding_dim)
        vector_store = FaissVectorStore(faiss_index=faiss_index)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # Build the vector index
        index = VectorStoreIndex.from_documents(documents,storage_context=storage_context,embed_model=embed_model)
        #index = VectorStoreIndex(nodes, storage_context=storage_context, embed_model=embed_model)

        # Persist to disk
        index.storage_context.persist()
        query_engine = index.as_query_engine(llm=openai_llm, similarity_top_k=7)
        print("Created and saved new FAISS index to ./storage")
        print("New FAISS index is ready for queries.")
        return {"status": "ok", "documents_indexed": len(documents)}
    
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

