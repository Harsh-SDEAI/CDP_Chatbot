/*
  CDP Chatbot — Database Migration Script
  Target: SQL Server

  Run this script once to create the required tables.
  It is safe to re-run (uses IF NOT EXISTS checks).
*/

-- ══════════════════════════════════════════════════════════════════════════════
--  1. CDPChatHistory  (main table — stores all chat Q&A and KB workflow)
-- ══════════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'CDPChatHistory')
BEGIN
    CREATE TABLE CDPChatHistory (
        id                  INT IDENTITY(1,1) PRIMARY KEY,
        ChatHistoryID       INT IDENTITY(1,1),       -- kept for KB export reference
        SessionId           NVARCHAR(100)   NULL,
        UserRegistrationId  INT             NULL,
        -- note: original column has a typo "UserRegistraionId" in some queries
        UserRegistraionId   AS UserRegistrationId,    -- computed alias for backward compat
        Question            NVARCHAR(MAX)   NULL,
        Answer              NVARCHAR(MAX)   NULL,
        SuggestedAnswer     NVARCHAR(MAX)   NULL,
        Status              NVARCHAR(50)    NULL,     -- 'PartiallyCorrect', 'InCorrect', etc.
        IsKBUpdated         BIT             NOT NULL  DEFAULT 0,
        PublishStatus       NVARCHAR(50)    NULL      DEFAULT NULL,  -- 'ReadyToPublish', 'Published'
        TimeStamp           DATETIME        NOT NULL  DEFAULT GETDATE()
    );

    PRINT 'Created table: CDPChatHistory';
END
ELSE
    PRINT 'Table CDPChatHistory already exists — skipped.';
GO


-- ══════════════════════════════════════════════════════════════════════════════
--  2. ChatHistoryIDInfo  (tracks last-processed KB export position)
-- ══════════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ChatHistoryIDInfo')
BEGIN
    CREATE TABLE ChatHistoryIDInfo (
        TableID         INT IDENTITY(1,1) PRIMARY KEY,
        ChatHistoryID   INT           NOT NULL,
        CreatedOn       DATETIME      NOT NULL  DEFAULT GETDATE()
    );

    PRINT 'Created table: ChatHistoryIDInfo';
END
ELSE
    PRINT 'Table ChatHistoryIDInfo already exists — skipped.';
GO


-- ══════════════════════════════════════════════════════════════════════════════
--  3. Indexes for common query patterns
-- ══════════════════════════════════════════════════════════════════════════════

-- KB export query: WHERE IsKBUpdated = 1 AND PublishStatus = 'ReadyToPublish'
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_CDPChatHistory_KBExport')
BEGIN
    CREATE NONCLUSTERED INDEX IX_CDPChatHistory_KBExport
        ON CDPChatHistory (IsKBUpdated, PublishStatus)
        INCLUDE (ChatHistoryID, Question, Answer, Status, SuggestedAnswer);

    PRINT 'Created index: IX_CDPChatHistory_KBExport';
END
GO

-- History listing: ORDER BY id DESC
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_CDPChatHistory_HistoryList')
BEGIN
    CREATE NONCLUSTERED INDEX IX_CDPChatHistory_HistoryList
        ON CDPChatHistory (id DESC)
        INCLUDE (SessionId, UserRegistrationId, Question, Answer, TimeStamp);

    PRINT 'Created index: IX_CDPChatHistory_HistoryList';
END
GO

PRINT '';
PRINT 'Migration complete.';
GO
