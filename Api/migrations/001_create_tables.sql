/*
  CDP Chatbot — Database Migration Script
  Target: PostgreSQL

  Run this script once to create the required tables.
  Safe to re-run (uses IF NOT EXISTS).
*/

-- 1. CDPChatHistory (stores all chat Q&A and KB workflow)

CREATE TABLE IF NOT EXISTS CDPChatHistory (
    id                  SERIAL PRIMARY KEY,
    SessionId           VARCHAR(100),
    UserRegistrationId  INTEGER,
    Question            TEXT,
    Answer              TEXT,
    SuggestedAnswer     TEXT,
    Status              VARCHAR(50),
    IsKBUpdated         BOOLEAN NOT NULL DEFAULT FALSE,
    PublishStatus       VARCHAR(50) DEFAULT NULL,
    TimeStamp           TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 2. ChatHistoryIDInfo (tracks last-processed KB export position)

CREATE TABLE IF NOT EXISTS ChatHistoryIDInfo (
    TableID         SERIAL PRIMARY KEY,
    ChatHistoryID   INTEGER NOT NULL,
    CreatedOn       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 3. Indexes for common query patterns

CREATE INDEX IF NOT EXISTS ix_cdpchathistory_kb_export
    ON CDPChatHistory (IsKBUpdated, PublishStatus);

CREATE INDEX IF NOT EXISTS ix_cdpchathistory_history_list
    ON CDPChatHistory (id DESC);
