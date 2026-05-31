"""
export_chat_api.py
==================
Standalone FastAPI service that lets the QA team download a CDPChatHistory
review spreadsheet for any date range, straight from the browser.

How QA uses it (once deployed):
    Open in a browser:
        http://<server>:<port>/export-chat?start=2026-01-01&end=2026-05-31
    The .xlsx downloads automatically to their device.

    Or use the auto-generated form at:
        http://<server>:<port>/docs

What it does:
    1. DB1 (chat DB): read ALL columns from CDPChatHistory for the date range.
    2. DB2 (CDP2000, different server): for each userid, look up the player's
       team via:
            SELECT TeamKey FROM Roster WHERE RosterID = ?
       then the team / player details via:
            SELECT TeamKey, Year, TournamentID, FirstName, LastName, Email
            FROM Team WHERE TeamKey = ?
       (combined here into a single Roster->Team JOIN, and cached per userid).
    3. Stream back one .xlsx with those player details in FRONT of the chat
       columns.

This service is intentionally SEPARATE from the main CDPAssist app. It reads
its two connection strings from a .env file (see .env.example) and imports
nothing from the main service.

Requires: see requirements-export.txt
    pip install -r requirements-export.txt

Run:
    uvicorn export_chat_api:app --host 0.0.0.0 --port 8100
"""

import io
import os
from datetime import datetime

import pyodbc
from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

# Two connection strings come from the .env file (values added manually).
CHAT_DB_CONNECTION_STRING = os.getenv("CHAT_DB_CONNECTION_STRING")
CDP2000_DB_CONNECTION_STRING = os.getenv("CDP2000_DB_CONNECTION_STRING")

# DB1 — chat history table
CHAT_TABLE     = "CDPChatHistory"
DATE_COLUMN    = "CreatedOn"            # column the date range filters on
USERID_COLUMN  = "UserRegistrationId"   # chat-side userid (maps to Roster.RosterID)

# DB2 — extra player columns we put in FRONT of the chat columns, in this order.
# (These match the Team SELECT list you specified.)
PLAYER_HEADERS = ["TeamKey", "Year", "TournamentID", "FirstName", "LastName", "Email"]

# Trailing blank review column
REVIEW_COLUMN_HEADER = "Review (Correct / Incorrect)"

# Filename prefix; the date range is appended automatically.
OUTPUT_FILE_PREFIX = "CDPChatHistory_review"

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
    CDP2000 by joining Roster -> Team:

        SELECT TeamKey FROM Roster WHERE RosterID = ?
        SELECT TeamKey, Year, TournamentID, FirstName, LastName, Email
          FROM Team WHERE TeamKey = ?

    Returns { user_id: {col: value, ...} } using PLAYER_HEADERS as keys.
    Userids with no matching roster/team row are simply omitted (blank in xlsx).
    Only the whitelisted columns above are ever selected.
    """
    details = {}
    if not user_ids:
        return details
    if not CDP2000_DB_CONNECTION_STRING:
        raise RuntimeError("CDP2000_DB_CONNECTION_STRING is not set in .env")

    # Roster.RosterID -> Team, combined into one query per userid.
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
    Layout: [player columns] + <all chat columns> + [Review]
    """
    headers = list(PLAYER_HEADERS) + list(chat_columns) + [REVIEW_COLUMN_HEADER]

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

    n_player = len(PLAYER_HEADERS)

    # Data rows
    for r_idx, row in enumerate(chat_rows, start=2):
        uid = row[userid_pos] if userid_pos is not None else None
        info = player_details.get(uid, {})

        # Player columns first
        for c_idx, header in enumerate(PLAYER_HEADERS, start=1):
            ws.cell(row=r_idx, column=c_idx, value=info.get(header))

        # Then the original chat columns
        for c_offset, value in enumerate(row):
            ws.cell(row=r_idx, column=n_player + 1 + c_offset, value=value)

    # Column widths
    wide = {"question", "answer", "suggestedanswer"}
    for col_idx, header in enumerate(headers, start=1):
        letter = ws.cell(row=1, column=col_idx).column_letter
        name = header.lower()
        if name in wide:
            ws.column_dimensions[letter].width = 60
        elif name == REVIEW_COLUMN_HEADER.lower():
            ws.column_dimensions[letter].width = 22
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
        "usage": "GET /export-chat?start=YYYY-MM-DD&end=YYYY-MM-DD",
        "docs": "/docs",
    }


@app.get("/export-chat")
def export_chat(
    start: str = Query(..., description="Start date (inclusive), YYYY-MM-DD"),
    end: str = Query(..., description="End date (inclusive), YYYY-MM-DD"),
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

    filename = f"{OUTPUT_FILE_PREFIX}_{start}_to_{end}.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
