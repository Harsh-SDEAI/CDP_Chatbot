-- ============================================================
-- CDP Chat Review - Database Migration Script
-- Target: SQL Server (MSSQL) - the SEPARATE "review" database that
--         export_chat_to_db.py writes into (NOT the chat/CDPApp DB).
-- Run this ONCE against that target database to create the
-- CDPChatReview table and its indexes.
-- ============================================================

-- CDPChatReview - one row per reviewed CDPChatHistory entry.
-- The source data (chat columns + UserRegistration details) is written and
-- refreshed by export_chat_to_db.py. The reviewer columns (Review / Topic /
-- Information) are left blank on insert and are NEVER overwritten on re-run,
-- so QA edits survive repeated exports.
--
-- NOTE on column types: FirstName/LastName/EmailId/TeamKey are stored as text;
-- SeasonYear/TournamentId/RosterId are assumed integer and the Week*Date
-- columns are assumed dates. If the real UserRegistration schema differs,
-- adjust these types to match.
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'CDPChatReview')
BEGIN
    CREATE TABLE CDPChatReview (
        ReviewId            INT IDENTITY(1,1) PRIMARY KEY,

        -- UserRegistrationId pulled to the front (matches the Excel layout)
        UserRegistrationId  INT NULL,

        -- UserRegistration details (looked up per userid)
        FirstName           NVARCHAR(255) NULL,
        LastName            NVARCHAR(255) NULL,
        SeasonYear          INT NULL,
        WeekStartDate       DATETIME NULL,
        WeekEndDate         DATETIME NULL,
        EmailId             NVARCHAR(255) NULL,
        TournamentId        INT NULL,
        RosterId            INT NULL,
        TeamKey             NVARCHAR(100) NULL,

        -- Carried over from CDPChatHistory (UserRegistrationId moved to front)
        ChatHistoryId       INT NOT NULL,
        SessionId           NVARCHAR(255) NULL,
        Question            NVARCHAR(MAX) NULL,
        Answer              NVARCHAR(MAX) NULL,
        CreatedOn           DATETIME NULL,
        Status              NVARCHAR(50) NULL,
        SuggestedAnswer     NVARCHAR(MAX) NULL,
        IsKBUpdated         BIT NULL,
        PublishStatus       NVARCHAR(50) NULL,

        -- Blank review columns for the QA reviewer (never overwritten on re-run)
        Review              NVARCHAR(50) NULL,   -- Correct / Incorrect
        Topic               NVARCHAR(255) NULL,
        Information         NVARCHAR(MAX) NULL,

        -- Bookkeeping: when the export script last wrote this row
        ExportedOn          DATETIME NOT NULL DEFAULT GETDATE()
    );
END
GO

-- Unique key on the source ChatHistoryId so the export can UPSERT
-- (one CDPChatReview row per CDPChatHistory row) and re-runs never duplicate.
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'UX_CDPChatReview_ChatHistoryId' AND object_id = OBJECT_ID('CDPChatReview'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX UX_CDPChatReview_ChatHistoryId
    ON CDPChatReview (ChatHistoryId);
END
GO

-- Helpful for browsing the review set by user and date.
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_CDPChatReview_User_CreatedOn' AND object_id = OBJECT_ID('CDPChatReview'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_CDPChatReview_User_CreatedOn
    ON CDPChatReview (UserRegistrationId, CreatedOn);
END
GO
