-- ============================================================================
-- migrations.sql  –  Database Migration Script for CDPConcierge
-- Run this in SSMS against your target database.
-- ============================================================================


-- ── 1. ConversationHistory Table ────────────────────────────────────────────

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


-- ── 2. IndexMetadata Table ──────────────────────────────────────────────────

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
    CREATE INDEX IX_IndexMetadata_UrlKey
        ON IndexMetadata(UrlKey);

    PRINT 'Created table: IndexMetadata';
END
ELSE
    PRINT 'Table already exists: IndexMetadata';
GO


-- ── 3. Migrate old IndexMetadata schema (Url → BaseUrl + Path) ─────────────
-- For existing databases upgrading from the old single-Url schema.

IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'IndexMetadata' AND COLUMN_NAME = 'Url'
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'IndexMetadata' AND COLUMN_NAME = 'BaseUrl'
    )
        ALTER TABLE IndexMetadata ADD BaseUrl NVARCHAR(MAX) NULL;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'IndexMetadata' AND COLUMN_NAME = 'Path'
    )
        ALTER TABLE IndexMetadata ADD Path NVARCHAR(MAX) NULL;

    UPDATE IndexMetadata
    SET BaseUrl = CASE
            WHEN CHARINDEX('/', Url, 9) > 0
            THEN LEFT(Url, CHARINDEX('/', Url, 9) - 1)
            ELSE Url
        END,
        Path = CASE
            WHEN CHARINDEX('/', Url, 9) > 0
            THEN SUBSTRING(Url, CHARINDEX('/', Url, 9), LEN(Url))
            ELSE '/'
        END
    WHERE BaseUrl IS NULL OR Path IS NULL;

    ALTER TABLE IndexMetadata ALTER COLUMN BaseUrl NVARCHAR(MAX) NOT NULL;
    ALTER TABLE IndexMetadata ALTER COLUMN Path NVARCHAR(MAX) NOT NULL;
    ALTER TABLE IndexMetadata DROP COLUMN Url;

    PRINT 'Migrated IndexMetadata: Url -> BaseUrl + Path';
END
ELSE
    PRINT 'IndexMetadata already has BaseUrl + Path columns';
GO
