"""
db.py — SQL Server I/O for ConversationHistory.

Only one table. No IndexMetadata, no content hashes — the knowledge base
lives in content.json, not in the database.
"""

import os
import logging
from datetime import datetime

import pyodbc
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

DB_CONN_STR: str = os.environ["SSMS_CONNECTION_STRING"]


def _conn() -> pyodbc.Connection:
    return pyodbc.connect(DB_CONN_STR)


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


def ensure_history_table_exists() -> None:
    with _conn() as conn:
        conn.execute(CREATE_HISTORY_TABLE_SQL)
        conn.commit()
    log.info("[DB] ConversationHistory verified.")


def save_qa(session_id: str, question: str, answer: str, followup: str | None = None) -> None:
    sql = """
        INSERT INTO ConversationHistory (SessionID, Question, Answer, FollowUpSuggestion, CreatedAt)
        VALUES (?, ?, ?, ?, ?)
    """
    with _conn() as c:
        c.execute(sql, session_id, question, answer, followup, datetime.utcnow())
        c.commit()


def get_history(session_id: str, pairs: int = 2) -> list[dict]:
    """Last `pairs` Q&A turns for the session, as OpenAI messages, in chronological order."""
    sql = f"""
        SELECT Question, Answer FROM (
            SELECT TOP {int(pairs)} Question, Answer, CreatedAt
            FROM ConversationHistory
            WHERE SessionID = ?
            ORDER BY CreatedAt DESC
        ) AS recent
        ORDER BY CreatedAt ASC
    """
    with _conn() as c:
        rows = c.execute(sql, session_id).fetchall()
    messages: list[dict] = []
    for q, a in rows:
        if q:
            messages.append({"role": "user", "content": q})
        if a:
            messages.append({"role": "assistant", "content": a})
    return messages


def get_history_with_limit(session_id: str, limit: int | None = None) -> list[dict]:
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
    with _conn() as c:
        rows = c.execute(sql, session_id).fetchall()
    messages: list[dict] = []
    for q, a in rows:
        if q:
            messages.append({"role": "user", "content": q})
        if a:
            messages.append({"role": "assistant", "content": a})
    return messages


def delete_session(session_id: str) -> int:
    sql = "DELETE FROM ConversationHistory WHERE SessionID = ?"
    with _conn() as c:
        cur = c.execute(sql, session_id)
        c.commit()
        return cur.rowcount
