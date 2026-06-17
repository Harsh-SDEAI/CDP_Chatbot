"""
db.py  –  SSMS (SQL Server) Integration
Handles all database operations for the RAG pipeline.

ConversationHistory Table:
Columns: ID, SessionID, Question, Answer, FollowUpSuggestion, CreatedAt

IndexMetadata Table:
Columns: ID, UrlKey, BaseUrl, Path, ContentHash, BuiltAt
"""

import os
import logging
from datetime import datetime

import pyodbc
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ── Connection ────────────────────────────────────────────────────────────────

DB_CONN_STR: str = os.environ["SSMS_CONNECTION_STRING"]
# Expected format in .env:
# SSMS_CONNECTION_STRING=DRIVER={ODBC Driver 17 for SQL Server};SERVER=your_server;DATABASE=your_db;UID=your_user;PWD=your_password


def _get_connection() -> pyodbc.Connection:
    """Return a fresh pyodbc connection."""
    return pyodbc.connect(DB_CONN_STR)


# ── DDL ───────────────────────────────────────────────────────────────────────

CREATE_HISTORY_TABLE_SQL = """
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'ConversationHistory'
)
BEGIN
    CREATE TABLE ConversationHistory (
        ID                 INT IDENTITY(1,1) PRIMARY KEY,
        SessionID          NVARCHAR(255)  NOT NULL,
        Question           NVARCHAR(MAX)  NULL,
        Answer             NVARCHAR(MAX)  NULL,
        FollowUpSuggestion NVARCHAR(MAX)  NULL,
        CreatedAt          DATETIME2      NOT NULL DEFAULT GETUTCDATE()
    );
    CREATE INDEX IX_ConversationHistory_SessionID ON ConversationHistory(SessionID);
END
"""

CREATE_INDEX_METADATA_TABLE_SQL = """
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'IndexMetadata'
)
BEGIN
    CREATE TABLE IndexMetadata (
        ID          INT IDENTITY(1,1) PRIMARY KEY,
        UrlKey      NVARCHAR(255)  NOT NULL,
        BaseUrl     NVARCHAR(MAX)  NOT NULL,
        Path        NVARCHAR(MAX)  NOT NULL,
        ContentHash NVARCHAR(255)  NOT NULL,
        BuiltAt     DATETIME2      NOT NULL DEFAULT GETUTCDATE()
    );
    CREATE INDEX IX_IndexMetadata_UrlKey ON IndexMetadata(UrlKey);
END
"""


def ensure_history_table_exists() -> None:
    """Create the ConversationHistory and IndexMetadata tables if they don't already exist."""
    with _get_connection() as conn:
        conn.execute(CREATE_HISTORY_TABLE_SQL)
        conn.execute(CREATE_INDEX_METADATA_TABLE_SQL)
        conn.commit()
    log.info("SSMS: ConversationHistory and IndexMetadata tables verified.")


# ── Save Q&A ──────────────────────────────────────────────────────────────────

def save_qa(
    session_id: str,
    question: str,
    answer: str,
    followup_suggestion: str | None = None,
) -> None:
    """
    Save Question + Answer + FollowUpSuggestion in a single row.
    Called once per query after Phase 3 completes.
    """
    sql = """
        INSERT INTO ConversationHistory (SessionID, Question, Answer, FollowUpSuggestion, CreatedAt)
        VALUES (?, ?, ?, ?, ?)
    """
    with _get_connection() as conn:
        conn.execute(sql, session_id, question, answer, followup_suggestion, datetime.utcnow())
        conn.commit()
    log.info("SSMS: Saved Q&A for session=%s followup=%s", session_id, followup_suggestion)


# ── Get History ───────────────────────────────────────────────────────────────

def get_history(session_id: str) -> list[dict]:
    """
    Return full conversation history for a session as a list of
    {"role": "user"/"assistant", "content": "..."}  dicts —
    ready to drop straight into the OpenAI messages array.
    Reconstructs user/assistant turns from Question/Answer columns.
    """
    # Return only the last 5 Q&A pairs to keep context focused
    sql = """
        SELECT Question, Answer FROM (
            SELECT TOP 5 Question, Answer, CreatedAt
            FROM ConversationHistory
            WHERE SessionID = ?
            ORDER BY CreatedAt DESC
        ) AS recent
        ORDER BY CreatedAt ASC
    """
    with _get_connection() as conn:
        rows = conn.execute(sql, session_id).fetchall()

    # Reconstruct alternating user/assistant messages for GPT context
    messages = []
    for row in rows:
        if row[0]:  # Question
            messages.append({"role": "user", "content": row[0]})
        if row[1]:  # Answer
            messages.append({"role": "assistant", "content": row[1]})

    return messages


def get_history_with_limit(session_id: str, limit: int | None = None) -> list[dict]:
    """
    Return conversation history for a session with configurable limit.
    If limit is None, returns all history.
    Used by the /history endpoint.
    """
    if limit:
        sql = f"""
            SELECT Question, Answer FROM (
                SELECT TOP {int(limit)} Question, Answer, CreatedAt
                FROM ConversationHistory
                WHERE SessionID = ?
                ORDER BY CreatedAt DESC
            ) AS recent
            ORDER BY CreatedAt ASC
        """
    else:
        sql = """
            SELECT Question, Answer
            FROM ConversationHistory
            WHERE SessionID = ?
            ORDER BY CreatedAt ASC
        """
    with _get_connection() as conn:
        rows = conn.execute(sql, session_id).fetchall()

    messages = []
    for row in rows:
        if row[0]:
            messages.append({"role": "user", "content": row[0]})
        if row[1]:
            messages.append({"role": "assistant", "content": row[1]})

    return messages


# ── Delete Session ────────────────────────────────────────────────────────────

def delete_session(session_id: str) -> int:
    """
    Remove all rows for *session_id* from ConversationHistory.
    Returns the number of rows deleted.
    """
    sql = "DELETE FROM ConversationHistory WHERE SessionID = ?"
    with _get_connection() as conn:
        cursor = conn.execute(sql, session_id)
        conn.commit()
        return cursor.rowcount


# ── Content Hash (IndexMetadata) ──────────────────────────────────────────────

def save_content_hash(url_key: str, base_url: str, path: str, content_hash: str) -> None:
    """
    Save a new content hash record for the given URL into IndexMetadata.
    Called every time a new index is built.
    """
    sql = """
        INSERT INTO IndexMetadata (UrlKey, BaseUrl, Path, ContentHash, BuiltAt)
        VALUES (?, ?, ?, ?, ?)
    """
    with _get_connection() as conn:
        conn.execute(sql, url_key, base_url, path, content_hash, datetime.utcnow())
        conn.commit()
    log.info("SSMS: Saved content hash for url_key=%s path=%s", url_key, path)


def get_latest_content_hash(url_key: str) -> str | None:
    """
    Return the most recently stored content hash for the given URL key.
    Returns None if no record exists yet.
    """
    sql = """
        SELECT TOP 1 ContentHash FROM IndexMetadata
        WHERE UrlKey = ?
        ORDER BY BuiltAt DESC
    """
    with _get_connection() as conn:
        row = conn.execute(sql, url_key).fetchone()
    return row[0] if row else None


def get_latest_indexed_path() -> str | None:
    """
    Return the path from the most recently built index.
    Used by /rag/query and scheduler to know which path to use.
    """
    sql = """
        SELECT TOP 1 Path FROM IndexMetadata
        ORDER BY BuiltAt DESC
    """
    with _get_connection() as conn:
        row = conn.execute(sql).fetchone()
    return row[0] if row else None