"""
export_chat_api.py
==================
Standalone FastAPI service that lets the QA team download a CDPChatHistory
review spreadsheet for any date range.

How QA uses it (once deployed):
    1. Open  http://<server>:<port>/docs
    2. Click "Authorize" and paste the X-API-Key value.
    3. Open the GET /export-chat endpoint, enter start + end dates
       (format YYYY-MM-DD), click Execute, then "Download file".

What it does:
    1. DB1 (chat DB): read ALL columns from CDPChatHistory for the date range.
    2. DB2 (CDP2000, different server): for each userid, look up the player's
       team via Roster -> Team:
            SELECT TeamKey FROM Roster WHERE RosterID = ?
            SELECT TeamKey, Year, TournamentID, FirstName, LastName, Email
              FROM Team WHERE TeamKey = ?
       (combined into a single Roster->Team JOIN inside CDP2000, cached per
       userid). RosterID == the chat-side UserRegistrationId, and is unique.
    3. Stream back one .xlsx with those player details in FRONT of the chat
       columns, plus trailing blank review columns:
            Review (Correct / Incorrect dropdown) | Topic | Information

NOTE on databases: the two databases live on different servers and are queried
on two separate connections. They are never joined together in one query. The
only JOIN (Roster->Team) happens entirely inside CDP2000.

NOTE on read-only: this script issues SELECT statements only. For real
enforcement, give the logins db_datareader and put ApplicationIntent=ReadOnly
in the connection strings.

This service is intentionally SEPARATE from the main CDPAssist app. It reads
its config from a .env file (see .env.example) and imports nothing from the
main service.

Requires: see requirements-export.txt
    pip install -r requirements-export.txt

Run:
    uvicorn export_chat_api:app --host 0.0.0.0 --port 8100
"""

import io
import os
import re
import html
from datetime import datetime

import pyodbc
from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

# Connection strings + API key come from the .env file (values added manually).
CHAT_DB_CONNECTION_STRING = os.getenv("CHAT_DB_CONNECTION_STRING")
CDP2000_DB_CONNECTION_STRING = os.getenv("CDP2000_DB_CONNECTION_STRING")
EXPORT_API_KEY = os.getenv("EXPORT_API_KEY")

# DB1 — chat history table
CHAT_TABLE     = "CDPChatHistory"
DATE_COLUMN    = "CreatedOn"            # column the date range filters on
USERID_COLUMN  = "UserRegistrationId"   # chat-side userid (== Roster.RosterID)

# DB2 — player columns put in FRONT of the chat columns, in this order
# (these match the Team SELECT list you specified).
PLAYER_HEADERS = ["TeamKey", "Year", "TournamentID", "FirstName", "LastName", "Email"]

# Userid pulled to the very FRONT (column A) for easy eyeballing against the
# Roster/Team join. It also still appears in its original spot among the chat
# columns (since we SELECT * from CDPChatHistory).
USERID_FRONT_HEADER = "UserRegistrationId"

# Trailing blank review columns
REVIEW_COLUMN_HEADER = "Review (Correct / Incorrect)"
EXTRA_REVIEW_HEADERS = ["Topic", "Information"]   # free-text columns for the reviewer

# Chat columns whose values hold HTML that should be flattened to plain text
HTML_TEXT_COLUMNS = {"answer", "question", "suggestedanswer"}

# Excel hard limit on characters per cell
EXCEL_MAX_CELL = 32767
TRUNCATE_MARKER = "…[truncated]"

# Filename prefix; the date range is appended automatically.
OUTPUT_FILE_PREFIX = "CDPAssist_prod_qna"

# ============================================================
# Value cleaning helpers
# ============================================================

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]*\n[ \t]*")


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
    Make a DB value safe for openpyxl:
      - flatten HTML on known text columns
      - strip illegal/control characters
      - truncate anything over Excel's per-cell limit
    Non-string values pass through untouched.
    """
    if not isinstance(value, str):
        return value

    if column_name.lower() in HTML_TEXT_COLUMNS:
        value = strip_html(value)

    value = ILLEGAL_CHARACTERS_RE.sub("", value)

    if len(value) > EXCEL_MAX_CELL:
        value = value[: EXCEL_MAX_CELL - len(TRUNCATE_MARKER)] + TRUNCATE_MARKER

    return value


# ============================================================
# Database access
# ============================================================


def fetch_chat_rows(start_date: str, end_date: str):
    """
    Fetch all columns from CDPChatHistory within the date range.
    end_date is inclusive of the whole day (< end_date + 1 day), so rows
    created at any time on end_date are included.
    """
    if not CHAT_DB_CONNECTION_STRING:
        raise RuntimeError("CHAT_DB_CONNECTION_STRING is not set in .env")

    conn = pyodbc.connect(CHAT_DB_CONNECTION_STRING)
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


def fetch_player_details(user_ids):
    """
    For each distinct userid, look up the player's team/player details from
    CDP2000 by joining Roster -> Team (RosterID is unique):

        SELECT TeamKey FROM Roster WHERE RosterID = ?
        SELECT TeamKey, Year, TournamentID, FirstName, LastName, Email
          FROM Team WHERE TeamKey = ?

    Returns { user_id: {col: value, ...} } keyed by PLAYER_HEADERS.
    Userids with no matching roster/team row are omitted (blank in xlsx).
    Only the whitelisted columns above are ever selected.
    """
    details = {}
    if not user_ids:
        return details
    if not CDP2000_DB_CONNECTION_STRING:
        raise RuntimeError("CDP2000_DB_CONNECTION_STRING is not set in .env")

    query = (
        "SELECT t.TeamKey, t.Year, t.TournamentID, t.FirstName, t.LastName, t.Email "
        "FROM Roster r "
        "INNER JOIN Team t ON r.TeamKey = t.TeamKey "
        "WHERE r.RosterID = ?"
    )

    conn = pyodbc.connect(CDP2000_DB_CONNECTION_STRING)
    try:
        cursor = conn.cursor()
        for uid in user_ids:
            cursor.execute(query, (uid,))
            row = cursor.fetchone()
            if row is not None:
                details[uid] = dict(zip(PLAYER_HEADERS, row))
        return details
    finally:
        conn.close()


# ============================================================
# Excel building
# ============================================================


def build_workbook_bytes(chat_columns, chat_rows, player_details):
    """
    Build the .xlsx in memory and return the raw bytes.
    Layout:
        [player cols] + <all chat cols> + [Review] + [Topic] + [Information]
    """
    headers = (
        [USERID_FRONT_HEADER]
        + list(PLAYER_HEADERS)
        + list(chat_columns)
        + [REVIEW_COLUMN_HEADER]
        + EXTRA_REVIEW_HEADERS
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Chat Review"

    # Header row styling
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="305496")
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    # Locate the userid column among the chat columns
    try:
        userid_pos = list(chat_columns).index(USERID_COLUMN)
    except ValueError:
        userid_pos = None

    # Front block = userid column + player columns
    n_front = 1 + len(PLAYER_HEADERS)

    # Data rows
    for r_idx, row in enumerate(chat_rows, start=2):
        uid = row[userid_pos] if userid_pos is not None else None
        info = player_details.get(uid, {})

        # Column A: userid pulled to the front
        ws.cell(row=r_idx, column=1, value=clean_value(uid, USERID_FRONT_HEADER))

        # Player columns next (cleaned for safety)
        for c_idx, header in enumerate(PLAYER_HEADERS, start=2):
            ws.cell(row=r_idx, column=c_idx, value=clean_value(info.get(header), header))

        # Then the original chat columns (cleaned)
        for c_offset, value in enumerate(row):
            col_name = chat_columns[c_offset]
            ws.cell(
                row=r_idx,
                column=n_front + 1 + c_offset,
                value=clean_value(value, col_name),
            )

    # Correct / Incorrect dropdown on the Review column for every data row
    review_col_idx = n_front + len(chat_columns) + 1
    review_col_letter = ws.cell(row=1, column=review_col_idx).column_letter
    if chat_rows:
        dv = DataValidation(
            type="list",
            formula1='"Correct,Incorrect"',
            allow_blank=True,
        )
        dv.add(f"{review_col_letter}2:{review_col_letter}{len(chat_rows) + 1}")
        ws.add_data_validation(dv)

    # Column widths
    wide = {"question", "answer", "suggestedanswer"}
    review_like = {REVIEW_COLUMN_HEADER.lower(), "information"}
    for col_idx, header in enumerate(headers, start=1):
        letter = ws.cell(row=1, column=col_idx).column_letter
        name = header.lower()
        if name in wide:
            ws.column_dimensions[letter].width = 60
        elif name in review_like:
            ws.column_dimensions[letter].width = 24
        elif name == "email":
            ws.column_dimensions[letter].width = 28
        else:
            ws.column_dimensions[letter].width = 18

    ws.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# FastAPI app
# ============================================================

app = FastAPI(title="CDP Chat Review Export", version="1.0")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(provided: str = Security(api_key_header)):
    """Reject any request without the correct X-API-Key header."""
    if not EXPORT_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Server is missing EXPORT_API_KEY config (set it in .env).",
        )
    if provided != EXPORT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key.")


def _validate_date(value: str, field: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be in YYYY-MM-DD format (got '{value}').",
        )
    return value


@app.get("/")
def root():
    return {
        "service": "CDP Chat Review Export",
        "usage": "GET /export-chat?start=YYYY-MM-DD&end=YYYY-MM-DD  (header X-API-Key required)",
        "docs": "/docs",
    }


@app.get("/export-chat", dependencies=[Security(require_api_key)])
def export_chat(
    start: str = Query(
        ...,
        description="Start date, inclusive. Format: YYYY-MM-DD (e.g. 2026-01-01)",
        examples=["2026-01-01"],
    ),
    end: str = Query(
        ...,
        description="End date, inclusive. Format: YYYY-MM-DD (e.g. 2026-05-31)",
        examples=["2026-05-31"],
    ),
):
    start = _validate_date(start, "start")
    end = _validate_date(end, "end")
    if start > end:
        raise HTTPException(status_code=400, detail="start must be <= end.")

    # 1. Chat rows
    try:
        chat_columns, chat_rows = fetch_chat_rows(start, end)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Chat DB read failed: {e}")

    # 2. Player details for the distinct userids we actually saw
    user_ids = set()
    if USERID_COLUMN in chat_columns:
        pos = list(chat_columns).index(USERID_COLUMN)
        user_ids = {r[pos] for r in chat_rows if r[pos] is not None}

    try:
        player_details = fetch_player_details(user_ids)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"CDP2000 DB read failed: {e}")

    # 3. Build the workbook
    try:
        data = build_workbook_bytes(chat_columns, chat_rows, player_details)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Excel build failed: {e}")

    filename = f"{OUTPUT_FILE_PREFIX}_{start}_{end}.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
