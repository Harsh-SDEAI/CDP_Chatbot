"""
export_chat_to_db.py
====================
Standalone script that copies CDPChatHistory review data for a date range into
a SEPARATE "review" database table (CDPChatReview) instead of an Excel file. It
is the database-writing twin of export_chat_api.py and shares the exact same
data + cleaning logic; only the destination differs.

What it does:
    1. Read the date range from the environment (EXPORT_START_DATE /
       EXPORT_END_DATE, format YYYY-MM-DD).
    2. Read ALL columns from CDPChatHistory in the source (chat) database for
       that range.
    3. For each userid, look up registration details from UserRegistration
       (same source DB), cached per userid:
            FirstName, LastName, SeasonYear, WeekStartDate, WeekEndDate,
            EmailId, TournamentId, RosterId, TeamKey
    4. UPSERT one row per chat entry into CDPChatReview in the TARGET database,
       keyed on ChatHistoryId:
         - new ChatHistoryId  -> INSERT
         - existing one       -> UPDATE the source-derived columns only
       The reviewer columns (Review / Topic / Information) are left blank on
       insert and are NEVER overwritten on re-run, so QA edits survive exports.

Layout written (mirrors the Excel export, UserRegistrationId pulled to front):
    [UserRegistrationId] + [UserRegistration cols] + [chat cols] +
    [Review] [Topic] [Information] (+ ExportedOn bookkeeping)

Config (all from the .env file - see .env.export-db.example):
    CHAT_DB_CONNECTION_STRING    source DB (CDPApp: CDPChatHistory + UserRegistration)
    TARGET_DB_CONNECTION_STRING  the OTHER DB that holds CDPChatReview
    EXPORT_START_DATE            inclusive start date, YYYY-MM-DD
    EXPORT_END_DATE              inclusive end date,   YYYY-MM-DD

This script is intentionally SEPARATE from the main CDPAssist app and from
export_chat_api.py. It imports nothing from them.

Requires: see requirements-export-db.txt
    pip install -r requirements-export-db.txt

Run (after creating CDPChatReview via migration_chat_review.sql):
    python export_chat_to_db.py
"""

import os
import re
import sys
import html
from datetime import datetime

import pyodbc
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

# SOURCE (chat) DB - holds CDPChatHistory AND UserRegistration. Same value the
# existing export_chat_api.py uses, so a single .env entry serves both.
CHAT_DB_CONNECTION_STRING = os.getenv("CHAT_DB_CONNECTION_STRING")
# TARGET DB - the OTHER database that holds the CDPChatReview table.
TARGET_DB_CONNECTION_STRING = os.getenv("TARGET_DB_CONNECTION_STRING")

# Date range comes from the environment (inclusive, YYYY-MM-DD).
EXPORT_START_DATE = os.getenv("EXPORT_START_DATE")
EXPORT_END_DATE = os.getenv("EXPORT_END_DATE")

# Source chat history table
CHAT_TABLE    = "CDPChatHistory"
DATE_COLUMN   = "CreatedOn"           # column the date range filters on
USERID_COLUMN = "UserRegistrationId"  # chat-side userid

# UserRegistration lookup (same database as the chat history).
USER_TABLE      = "UserRegistration"
USER_KEY_COLUMN = "UserRegistrationId"
USERREG_COLUMNS = [
    "FirstName",
    "LastName",
    "SeasonYear",
    "WeekStartDate",
    "WeekEndDate",
    "EmailId",
    "TournamentId",
    "RosterId",
    "TeamKey",
]

# CDPChatHistory columns carried into CDPChatReview, in order. UserRegistrationId
# is deliberately excluded here because it is written once at the front (matching
# the Excel export, which moves it to column A).
CHAT_CARRY_COLUMNS = [
    "ChatHistoryId",
    "SessionId",
    "Question",
    "Answer",
    "CreatedOn",
    "Status",
    "SuggestedAnswer",
    "IsKBUpdated",
    "PublishStatus",
]

# Target table + the natural key the upsert matches on.
TARGET_TABLE = "CDPChatReview"
UPSERT_KEY   = "ChatHistoryId"

# Source-derived target columns, in write order: userid (front) + registration
# details + carried chat columns. The reviewer columns (Review / Topic /
# Information) and ExportedOn are handled by the table defaults and never
# overwritten here.
SRC_COLUMNS = [USERID_COLUMN] + USERREG_COLUMNS + CHAT_CARRY_COLUMNS

# Chat columns whose values hold HTML that should be flattened to plain text,
# exactly as the Excel export does.
HTML_TEXT_COLUMNS = {"answer", "question", "suggestedanswer"}


# ============================================================
# Value cleaning helpers
# Same behavior as export_chat_api.py, minus the Excel-only 32767-char cell
# truncation - the DB text columns are NVARCHAR(MAX), so there is no per-cell
# limit to honor.
# ============================================================

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]*\n[ \t]*")
# Control chars Excel rejects; harmless to strip before a DB write too.
# (Matches openpyxl's ILLEGAL_CHARACTERS_RE: 0x00-0x08, 0x0B-0x0C, 0x0E-0x1F.)
_ILLEGAL_RE = re.compile(r"[\000-\010\013\014\016-\037]")


def strip_html(text: str) -> str:
    """Flatten stored HTML into readable plain text."""
    # Turn common block/break tags into newlines so structure survives.
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*(p|div|li|tr|h[1-6])\s*>", "\n", text)
    # Drop all remaining tags, then unescape entities (&amp; -> & etc.).
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    # Tidy whitespace.
    text = _WS_RE.sub("\n", text)
    return text.strip()


def clean_value(value, column_name: str = ""):
    """
    Make a DB value safe to re-store:
      - flatten HTML on known text columns
      - strip illegal/control characters
    Non-string values pass through untouched.
    """
    if not isinstance(value, str):
        return value

    if column_name.lower() in HTML_TEXT_COLUMNS:
        value = strip_html(value)

    value = _ILLEGAL_RE.sub("", value)
    return value


# ============================================================
# Source database access
# ============================================================


def _require(value, name):
    if not value:
        raise RuntimeError(f"{name} is not set in .env")
    return value


def fetch_chat_rows(start_date, end_date):
    """
    Fetch all columns from CDPChatHistory within the date range.
    end_date is inclusive of the whole day (< end_date + 1 day), so rows
    created at any time on end_date are included.
    """
    conn = pyodbc.connect(_require(CHAT_DB_CONNECTION_STRING, "CHAT_DB_CONNECTION_STRING"))
    try:
        cursor = conn.cursor()
        query = (
            f"SELECT * FROM {CHAT_TABLE} "
            f"WHERE {DATE_COLUMN} >= ? "
            f"AND {DATE_COLUMN} < DATEADD(DAY, 1, CAST(? AS DATE)) "
            f"ORDER BY {DATE_COLUMN} ASC"
        )
        cursor.execute(query, (start_date, end_date))
        columns = [col[0] for col in cursor.description]
        rows = [list(r) for r in cursor.fetchall()]
        return columns, rows
    finally:
        conn.close()


def fetch_user_details(user_ids):
    """
    For each distinct userid, look up registration details from UserRegistration
    in the same (chat) database. Returns { user_id: {col: value, ...} } keyed by
    USERREG_COLUMNS. Userids with no matching registration row are omitted.
    Only the whitelisted columns above are ever selected.
    """
    details = {}
    if not user_ids:
        return details

    select_list = ", ".join(USERREG_COLUMNS)
    query = (
        f"SELECT {select_list} FROM {USER_TABLE} "
        f"WHERE {USER_KEY_COLUMN} = ?"
    )

    conn = pyodbc.connect(_require(CHAT_DB_CONNECTION_STRING, "CHAT_DB_CONNECTION_STRING"))
    try:
        cursor = conn.cursor()
        for uid in user_ids:
            cursor.execute(query, (uid,))
            row = cursor.fetchone()
            if row is not None:
                details[uid] = dict(zip(USERREG_COLUMNS, row))
        return details
    finally:
        conn.close()


# ============================================================
# Row assembly
# ============================================================


def build_target_rows(chat_columns, chat_rows, user_details):
    """
    Turn raw chat rows + user details into ordered dicts keyed by the
    CDPChatReview source columns (SRC_COLUMNS). Chat columns are matched by
    name (case-insensitive), so extra columns in the source are ignored and
    missing ones become NULL. Rows with no usable ChatHistoryId are skipped
    (there would be nothing to upsert on).
    """
    col_index = {name.lower(): i for i, name in enumerate(chat_columns)}

    def chat_get(row, name):
        i = col_index.get(name.lower())
        return row[i] if i is not None else None

    target_rows = []
    skipped = 0
    for row in chat_rows:
        chat_id = chat_get(row, UPSERT_KEY)
        if chat_id is None:
            skipped += 1
            continue

        uid = chat_get(row, USERID_COLUMN)
        info = user_details.get(uid, {})

        record = {}
        # UserRegistrationId pulled to the front
        record[USERID_COLUMN] = clean_value(uid, USERID_COLUMN)
        # UserRegistration details
        for c in USERREG_COLUMNS:
            record[c] = clean_value(info.get(c), c)
        # Carried chat columns (HTML flattened on the known text columns)
        for c in CHAT_CARRY_COLUMNS:
            record[c] = clean_value(chat_get(row, c), c)
        target_rows.append(record)

    return target_rows, skipped


# ============================================================
# Target database write (UPSERT on ChatHistoryId)
# ============================================================


def upsert_rows(target_rows):
    """
    UPSERT each record into CDPChatReview keyed on ChatHistoryId. The UPDATE
    path refreshes the source-derived columns only; the reviewer columns
    (Review / Topic / Information) are never touched. Returns (inserted, updated).
    The whole run is one transaction: it commits on success, rolls back on error.
    """
    if not target_rows:
        return 0, 0

    update_cols = [c for c in SRC_COLUMNS if c != UPSERT_KEY]
    update_sql = (
        f"UPDATE {TARGET_TABLE} SET "
        + ", ".join(f"{c} = ?" for c in update_cols)
        + ", ExportedOn = GETDATE() "
        + f"WHERE {UPSERT_KEY} = ?"
    )
    insert_sql = (
        f"INSERT INTO {TARGET_TABLE} ({', '.join(SRC_COLUMNS)}) "
        f"VALUES ({', '.join('?' for _ in SRC_COLUMNS)})"
    )
    exists_sql = f"SELECT 1 FROM {TARGET_TABLE} WHERE {UPSERT_KEY} = ?"

    conn = pyodbc.connect(_require(TARGET_DB_CONNECTION_STRING, "TARGET_DB_CONNECTION_STRING"))
    inserted = updated = 0
    try:
        cursor = conn.cursor()
        for rec in target_rows:
            cursor.execute(exists_sql, (rec[UPSERT_KEY],))
            if cursor.fetchone() is not None:
                params = [rec[c] for c in update_cols] + [rec[UPSERT_KEY]]
                cursor.execute(update_sql, params)
                updated += 1
            else:
                cursor.execute(insert_sql, [rec[c] for c in SRC_COLUMNS])
                inserted += 1
        conn.commit()
        return inserted, updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================
# Date validation + entry point
# ============================================================


def _validate_date(value, field):
    if not value:
        raise RuntimeError(
            f"{field} is not set in .env (expected YYYY-MM-DD, e.g. 2026-01-01)."
        )
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise RuntimeError(f"{field} must be in YYYY-MM-DD format (got '{value}').")
    return value


def main():
    start = _validate_date(EXPORT_START_DATE, "EXPORT_START_DATE")
    end = _validate_date(EXPORT_END_DATE, "EXPORT_END_DATE")
    if start > end:
        raise RuntimeError("EXPORT_START_DATE must be <= EXPORT_END_DATE.")

    print(f"[export-db] Range {start} .. {end} (inclusive)")

    # 1. Source chat rows
    chat_columns, chat_rows = fetch_chat_rows(start, end)
    print(f"[export-db] Read {len(chat_rows)} chat row(s) from {CHAT_TABLE}.")

    # 2. UserRegistration details for the distinct userids actually seen
    col_index = {c.lower(): i for i, c in enumerate(chat_columns)}
    upos = col_index.get(USERID_COLUMN.lower())
    user_ids = set()
    if upos is not None:
        user_ids = {r[upos] for r in chat_rows if r[upos] is not None}
    user_details = fetch_user_details(user_ids)
    print(
        f"[export-db] Looked up {len(user_details)} of {len(user_ids)} "
        f"userid(s) in {USER_TABLE}."
    )

    # 3. Assemble + upsert into the target DB
    target_rows, skipped = build_target_rows(chat_columns, chat_rows, user_details)
    inserted, updated = upsert_rows(target_rows)

    summary = f"[export-db] Done. Inserted {inserted}, updated {updated}"
    if skipped:
        summary += f", skipped {skipped} (no {UPSERT_KEY})"
    summary += f" into {TARGET_TABLE}."
    print(summary)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[export-db] ERROR: {e}", file=sys.stderr)
        sys.exit(1)
