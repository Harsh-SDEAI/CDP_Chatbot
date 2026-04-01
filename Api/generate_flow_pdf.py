"""Generate PDF with code flow and overview flow diagrams."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

output_path = "concierge_storage/Concierge_RAG_Flow.pdf"

doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm,
                        leftMargin=15*mm, rightMargin=15*mm)

styles = getSampleStyleSheet()

# Custom styles
title_style = ParagraphStyle("Title2", parent=styles["Title"], fontSize=18,
                              textColor=HexColor("#2980B9"), spaceAfter=10)
section_style = ParagraphStyle("Section", parent=styles["Heading2"], fontSize=14,
                                textColor=HexColor("#FFFFFF"), backColor=HexColor("#2980B9"),
                                spaceAfter=8, spaceBefore=12, leftIndent=5, borderPadding=(5, 5, 5, 5))
sub_style = ParagraphStyle("Sub", parent=styles["Heading3"], fontSize=11,
                            textColor=HexColor("#2980B9"), spaceAfter=4, spaceBefore=8)
body_style = ParagraphStyle("Body2", parent=styles["Normal"], fontSize=10, spaceAfter=4, leading=14)
code_style = ParagraphStyle("Code", fontName="Courier", fontSize=8, backColor=HexColor("#F0F0F0"),
                             leftIndent=5, rightIndent=5, spaceAfter=6, spaceBefore=4, leading=11,
                             borderPadding=(5, 5, 5, 5))

elements = []

# ── Title ──
elements.append(Paragraph("Cooperstown Concierge - RAG Chatbot Flow", title_style))
elements.append(Spacer(1, 5*mm))

# ── Flow 1: Overview ──
elements.append(Paragraph("Flow 1: Overview Flow (Simple Summary)", section_style))
elements.append(Spacer(1, 3*mm))
elements.append(Paragraph(
    "High-level flow showing how each user query is processed through "
    "3 layers of free classification before any GPT call is made.", body_style))

overview_flow = """USER SENDS MESSAGE
       |
       v
+----------------------------+
| Step 1: Pure Greeting?     |---- YES ----> Return greeting (0 LLM calls)
+----------------------------+
       | NO
       v
+----------------------------+
| Step 2: Has Cooperstown    |---- NO -----> Return fallback (0 LLM calls)
|         keyword?           |
+----------------------------+
       | YES
       v
+----------------------------+
| Step 3: FAISS search       |
|   Best score > 1.5?        |---- YES ----> Return fallback (0 LLM calls)
+----------------------------+
       | NO (relevant)
       v
+----------------------------+
| Load chat history (DB)     |
| Load top 5 chunks          |
+----------------------------+
       |
       v
+----------------------------+
| Step 4: 1 GPT CALL         |
| Answer + Follow-up         |
+----------------------------+
       |
       v
+----------------------------+
| Save to DB + Return        |
+----------------------------+"""

elements.append(Preformatted(overview_flow, code_style))
elements.append(Spacer(1, 3*mm))

elements.append(Paragraph("Token Usage Summary", sub_style))
table_data = [
    ["Query Type", "LLM Calls", "Tokens Used", "Example"],
    ["Greeting", "0", "0", '"hi", "hello"'],
    ["No Keyword", "0", "0", '"what is bitcoin"'],
    ["FAISS > 1.5", "0", "0", "Unrelated topic"],
    ["Relevant", "1", "~350 max", '"game time"'],
]
t = Table(table_data, colWidths=[45*mm, 30*mm, 30*mm, 45*mm])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2980B9")),
    ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F5F5F5")]),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
elements.append(t)

# ── Flow 2: Code-Wise ──
elements.append(Spacer(1, 5*mm))
elements.append(Paragraph("Flow 2: Code-Wise Flow (Detailed)", section_style))

elements.append(Paragraph("Server Startup", sub_style))
startup_flow = """SERVER STARTS (concierge_api.py)
       |
       v
lifespan() runs on startup
  |-- _load_faiss()
  |     |-- index.faiss exists? -> Load it
  |     +-- Not exists? -> Create new IndexFlatL2(1536)
  |
  |-- _rebuild_faiss_if_needed()
  |     |-- No meta? -> Auto-index all .md files
  |     +-- Avg chunk > 400 words?
  |           -> Backup old files to faiss_backup/
  |           -> Rebuild with 300-word chunks
  |
  +-- Scheduler starts
        -> check_monitored_urls() every 1 hour"""
elements.append(Preformatted(startup_flow, code_style))

elements.append(Paragraph("Step 1: Query Truncation + Pure Greeting Check", sub_style))
step1_flow = """POST /rag/query  <-- {query, top_k, asked_questions, session_id}
       |
       v
Query Truncation:
  if len(query.split()) > 50:
      query = first 50 words only
       |
       v
Pure Greeting Check:
  greeting_words = {hi, hello, hey, hii, helo, ...}
  Remove greeting words from query
  If nothing left -> PURE GREETING

  "hi"              -> [] left -> GREETING -> return response (0 tokens)
  "hi, game times"  -> ["game","times"] left -> NOT greeting -> continue"""
elements.append(Preformatted(step1_flow, code_style))

elements.append(Paragraph("Step 2: Binary Keyword Relevance Check", sub_style))
step2_flow = """RELEVANT_KEYWORDS = {
  "game", "food", "hotel", "park", "cooperstown",
  "travel", "dining", "camp", "baseball", "shop",
  "brewery", "activity", "ticket", "weather", ...
}

query_words = set(query.lower().split())
overlap = query_words & RELEVANT_KEYWORDS

"what is bitcoin"  -> overlap = {} -> FALLBACK (0 tokens)
"game time"        -> overlap = {game, time} -> PASS"""
elements.append(Preformatted(step2_flow, code_style))

elements.append(Paragraph("Step 3: FAISS Search + Score Check", sub_style))
step3_flow = """search_index(query, top_k=5)
  |
  |-- _get_embedding(query)
  |     -> OpenAI text-embedding-3-small
  |     -> returns [0.02, -0.04, ...] (1536 dimensions)
  |
  |-- _faiss_index.search(query_vector, k=5)
  |     -> L2 distance with all 15 chunk vectors
  |     -> returns 5 closest + distances (scores)
  |
  +-- results: [{text, score, file_id}, ...]

Console prints:
  Chunk 1 | Score: 0.52 | Game times are 9 AM...
  Chunk 2 | Score: 0.78 | Activities include...

best_score = chunks[0].score
If best_score > 1.5 -> FALLBACK (0 tokens)
If best_score <= 1.5 -> RELEVANT -> continue"""
elements.append(Preformatted(step3_flow, code_style))

elements.append(Paragraph("Chat History from Database", sub_style))
db_flow = """Load last 5 Q&A pairs from SQL Server:

  SELECT TOP 5 question, answer
  FROM chat_history
  WHERE session_id = ?
  ORDER BY id DESC

Reverse order (oldest first) for conversation context:
  {user: Q1}, {assistant: A1}
  {user: Q2}, {assistant: A2}
  ... up to 5 pairs"""
elements.append(Preformatted(db_flow, code_style))

elements.append(Paragraph("Step 4: Single GPT Call (Answer + Follow-up)", sub_style))
step4_flow = """messages = [
  {system: System Prompt + FOLLOW-UP instruction
           + avoid list (asked_questions)},
  {user: Q1}, {assistant: A1},   <-- DB history
  {user: Q2}, {assistant: A2},
  {user: "Context:\\n{chunks}\\n\\nQuestion: game time"}
]

ai.chat.completions.create(
  model="gpt-4o-mini",
  max_completion_tokens=350,
  temperature=0.3
)

GPT returns:
  "Games start at **9:00 AM**...
  [FOLLOWUP]
  What dining options are near the park?"

Split response on [FOLLOWUP]:
  answer   = "Games start at 9:00 AM..."
  followup = "What dining options are near the park?"

Return to Streamlit:
{
  "answer": "Games start at 9:00 AM...",
  "sources": ["cooperstowndreamspark_com_..."],
  "chunks_used": 5,
  "followup_questions": ["What dining options..."],
  "token_usage": {input: X, output: Y, total: Z}
}

Streamlit then:
  1. Displays answer in chat
  2. Shows follow-up button
  3. POST /chat/save -> saves Q&A to SQL Server
  4. Adds question to asked_questions list"""
elements.append(Preformatted(step4_flow, code_style))

# ── LLM Comparison ──
elements.append(Spacer(1, 5*mm))
elements.append(Paragraph("LLM Call Comparison: Before vs After", section_style))

elements.append(Paragraph("Before (3 LLM Calls)", sub_style))
before_flow = """User query
  |-> LLM Call 1: Keyword Extraction (gpt-4o-mini, 50 tokens)
  |-> Multi-query FAISS search (4-5 searches)
  |-> Classification check
  |-> LLM Call 2: Main Answer (gpt-4o-mini, 300 tokens)
  |-> LLM Call 3: Follow-up (gpt-4o-mini, 150 tokens)
  Total: 3 LLM calls per relevant query"""
elements.append(Preformatted(before_flow, code_style))

elements.append(Paragraph("After (1 LLM Call)", sub_style))
after_flow = """User query
  |-> Step 1: Greeting check (FREE)
  |-> Step 2: Binary keyword check (FREE)
  |-> Step 3: FAISS search + score check (FREE)
  |-> Step 4: 1 GPT call - Answer + Follow-up (350 tokens)
  Total: 1 LLM call per relevant query"""
elements.append(Preformatted(after_flow, code_style))

elements.append(Spacer(1, 3*mm))
elements.append(Paragraph("Savings Summary", sub_style))

savings_data = [
    ["Scenario", "Before LLM", "After LLM", "Before Tokens", "After Tokens"],
    ["Greeting", "1 call", "0 calls", "~100", "0"],
    ["Irrelevant", "1 call", "0 calls", "~100", "0"],
    ["Relevant", "3 calls", "1 call", "~500", "~350"],
    ["100 relevant Qs", "300 calls", "100 calls", "~50,000", "~35,000"],
]
t2 = Table(savings_data, colWidths=[32*mm, 28*mm, 28*mm, 32*mm, 32*mm])
t2.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2980B9")),
    ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F5F5F5")]),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
elements.append(t2)

elements.append(Spacer(1, 5*mm))
elements.append(Paragraph("<b>Key Savings:</b>", body_style))
elements.append(Paragraph("- 66% fewer LLM calls for relevant queries (3 -> 1)", body_style))
elements.append(Paragraph("- 100% fewer LLM calls for greetings and irrelevant queries (1 -> 0)", body_style))
elements.append(Paragraph("- ~30% fewer tokens per relevant query (500 -> 350)", body_style))

# ── Build PDF ──
doc.build(elements)
print(f"PDF saved to: {output_path}")
