-- ============================================================
-- CDP Chatbot - Full Database Migration Script
-- Target: SQL Server (MSSQL)
-- Run this script once against a fresh database to create
-- all tables and indexes required by the application.
-- ============================================================

-- 1. CDPChatHistory — main table for all chat interactions
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'CDPChatHistory')
BEGIN
    CREATE TABLE CDPChatHistory (
        ChatHistoryId       INT IDENTITY(1,1) PRIMARY KEY,
        SessionId           NVARCHAR(255) NOT NULL,
        UserRegistrationId  INT NOT NULL,
        Question            NVARCHAR(MAX) NULL,
        Answer              NVARCHAR(MAX) NULL,
        CreatedOn           DATETIME NOT NULL DEFAULT GETDATE(),
        Status              NVARCHAR(50) NULL,
        SuggestedAnswer     NVARCHAR(MAX) NULL,
        IsKBUpdated         BIT NOT NULL DEFAULT 0,
        PublishStatus       NVARCHAR(50) NULL
    );
END
GO

-- 2. Indexes on CDPChatHistory for the application's query patterns

-- /ChatHistory & /SessionHistory: filter by user, group/filter by session
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_CDPChatHistory_User_Session' AND object_id = OBJECT_ID('CDPChatHistory'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_CDPChatHistory_User_Session
    ON CDPChatHistory (UserRegistrationId, SessionId)
    INCLUDE (Question, CreatedOn);
END
GO

-- export_qa_pairs_job: filter by IsKBUpdated + PublishStatus
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_CDPChatHistory_KBUpdate' AND object_id = OBJECT_ID('CDPChatHistory'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_CDPChatHistory_KBUpdate
    ON CDPChatHistory (IsKBUpdated, PublishStatus)
    INCLUDE (ChatHistoryId, Question, Answer, Status, SuggestedAnswer);
END
GO
