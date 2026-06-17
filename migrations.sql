-- ============================================================================
-- migrations.sql — Cooperstown Concierge Chatbot
-- Run this in SSMS against the target database.
-- Only one table is needed: ConversationHistory.
-- ============================================================================

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
    CREATE INDEX IX_ConversationHistory_SessionID
        ON ConversationHistory(SessionID);

    PRINT 'Created table: ConversationHistory';
END
ELSE
    PRINT 'Table already exists: ConversationHistory';
GO
