# Cooperstown Concierge Chatbot

A single-page chatbot for Cooperstown Dreams Park visitors. Answers questions
about accommodations, dining, attractions, services, and trip planning using a
hand-curated knowledge base.

## Architecture

- **No scraping. No RAG. No vector DB.** The full knowledge base lives in
  `content.json` and is included in the system prompt on every chat call.
  OpenAI's automatic prompt caching keeps the static prefix cheap.
- **Follow-up suggestions are constrained** to the page's actual question
  list. The model picks one verbatim or returns `null` — never invents.
- **Conversation history** is persisted in SQL Server. The last 2 Q&A pairs
  are injected into each chat call.

## Files

| File | Purpose |
| --- | --- |
| `app.py` | FastAPI app + `/rag/query`, `/history`, `/health` endpoints |
| `db.py` | SQL Server I/O for `ConversationHistory` |
| `content.json` | Knowledge base (intro + 50 FAQs) — **edit this to update content** |
| `migrations.sql` | DDL for `ConversationHistory` |
| `requirements.txt` | Python deps |
| `web.config` | IIS / httpPlatformHandler deployment |

## Environment variables

Set these in a `.env` file or the deployment environment:

```
OPENAI_API_KEY=sk-...
API_SECRET_KEY=<your bearer token>
SSMS_CONNECTION_STRING=DRIVER={ODBC Driver 17 for SQL Server};SERVER=...;DATABASE=...;UID=...;PWD=...
LOG_DIR=logs   # optional, defaults to ./logs
```

## Endpoints

All endpoints except `/health` require `Authorization: Bearer <API_SECRET_KEY>`.

| Method | Path | Body / Query | Response |
| --- | --- | --- | --- |
| POST | `/rag/query` | `{ session_id, user_question }` | `{ session_id, answer, followup_suggestion }` |
| GET | `/history/{session_id}` | `?limit=N` (optional) | `{ session_id, history: [{role, content}, ...] }` |
| DELETE | `/history/{session_id}/clear` | — | `{ session_id, rows_deleted }` |
| GET | `/health` | — | `{ status: "ok" }` |

## Updating the knowledge base

Edit `content.json` directly and redeploy. There is no scraper to maintain
and no index to rebuild. Each entry is:

```json
{
  "category": "Food/Dining",
  "question": "Are there any recommended pizza places in Cooperstown?",
  "answer": "**New York Pizzeria** offers..."
}
```

Each question string must be unique — it is also used as the value the model
returns in `followup_suggestion`.

## Running locally

```
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Hit `http://localhost:8000/docs` for the interactive API explorer.
