import streamlit as st
import requests
import re
from datetime import datetime

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Content Manager",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design System CSS ─────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Variables ── */
:root {
    --bg:           #f2f3f7;
    --surface:      rgba(255,255,255,0.72);
    --surface-2:    rgba(255,255,255,0.50);
    --surface-3:    rgba(255,255,255,0.30);
    --border:       rgba(0,0,0,0.07);
    --border-2:     rgba(0,0,0,0.12);
    --text:         #1a1a2e;
    --text-2:       #5a5a7a;
    --text-3:       #9898b8;
    --accent:       #4f46e5;
    --accent-light: rgba(79,70,229,0.10);
    --accent-glow:  rgba(79,70,229,0.25);
    --success:      #059669;
    --danger:       #dc2626;
    --warning:      #d97706;
    --radius:       14px;
    --radius-lg:    20px;
    --shadow-sm:    0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow:       0 4px 16px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.04);
    --shadow-lg:    0 12px 40px rgba(0,0,0,0.12), 0 4px 12px rgba(0,0,0,0.06);
    --blur:         backdrop-filter: blur(16px) saturate(180%);
}

/* ── Base ── */
html, body, [class*="css"], .stApp {
    font-family: 'Outfit', sans-serif !important;
    background: var(--bg) !important;
}
.main .block-container {
    padding: 2rem 2.5rem 3rem !important;
    max-width: 1080px !important;
}

/* ── Animated background ── */
.stApp::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
        radial-gradient(ellipse 800px 600px at 10% 20%, rgba(79,70,229,0.06) 0%, transparent 60%),
        radial-gradient(ellipse 600px 500px at 85% 70%, rgba(139,92,246,0.05) 0%, transparent 60%),
        radial-gradient(ellipse 500px 400px at 50% 50%, rgba(99,102,241,0.03) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.80) !important;
    backdrop-filter: blur(20px) saturate(180%) !important;
    border-right: 1px solid var(--border-2) !important;
    box-shadow: 2px 0 20px rgba(0,0,0,0.05) !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.5rem !important;
}
[data-testid="stSidebar"] * { color: var(--text) !important; }
[data-testid="stSidebar"] .stRadio > div { gap: 2px !important; }
[data-testid="stSidebar"] .stRadio label {
    font-size: 0.875rem !important;
    font-weight: 400 !important;
    padding: 9px 14px !important;
    border-radius: 10px !important;
    transition: background 0.15s !important;
    color: var(--text-2) !important;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: var(--accent-light) !important;
    color: var(--accent) !important;
}
[data-testid="stSidebar"] input {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-2) !important;
    border-radius: 10px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.75rem !important;
    color: var(--text) !important;
}
[data-testid="stSidebar"] hr {
    border-color: var(--border) !important;
    margin: 1rem 0 !important;
}

/* ── Typography ── */
h1 {
    font-size: 1.75rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.04em !important;
    color: var(--text) !important;
    margin-bottom: 0.25rem !important;
}
h2 {
    font-size: 1.2rem !important;
    font-weight: 600 !important;
    color: var(--text) !important;
}
h3 {
    font-size: 1rem !important;
    font-weight: 600 !important;
    color: var(--text) !important;
}
p, li { color: var(--text-2) !important; }
.stCaption, [data-testid="stCaptionContainer"] {
    color: var(--text-3) !important;
    font-size: 0.78rem !important;
}

/* ── Glass Cards (via markdown containers) ── */
.glass-card {
    background: var(--surface);
    backdrop-filter: blur(16px) saturate(180%);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1.5rem;
    box-shadow: var(--shadow);
    margin-bottom: 1rem;
}
.glass-card-sm {
    background: var(--surface);
    backdrop-filter: blur(16px) saturate(180%);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem 1.25rem;
    box-shadow: var(--shadow-sm);
}

/* ── Page header block ── */
.page-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 1.75rem;
    padding-bottom: 1.25rem;
    border-bottom: 1px solid var(--border);
}
.page-header-icon {
    width: 44px; height: 44px;
    background: var(--accent-light);
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem;
}
.page-header-title { font-size: 1.5rem; font-weight: 700; color: var(--text); letter-spacing: -0.03em; }
.page-header-sub { font-size: 0.8rem; color: var(--text-3); margin-top: 1px; }

/* ── Stat chips ── */
.stat-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 1.25rem; }
.stat-chip {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--surface);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-2);
    border-radius: 30px;
    padding: 6px 16px;
    font-size: 0.8rem;
    color: var(--text-2);
    font-family: 'Outfit', sans-serif;
    box-shadow: var(--shadow-sm);
}
.stat-chip strong { color: var(--accent); font-weight: 600; }
.stat-chip .dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--accent);
    opacity: 0.7;
}

/* ── Buttons ── */
.stButton > button {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    border-radius: 10px !important;
    transition: all 0.18s ease !important;
    letter-spacing: 0.01em !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(145deg, #5b52f0, #4338ca) !important;
    border: none !important;
    color: #fff !important;
    box-shadow: 0 2px 8px var(--accent-glow) !important;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px var(--accent-glow) !important;
}
.stButton > button[kind="primary"]:active { transform: translateY(0) !important; }
.stButton > button[kind="secondary"] {
    background: var(--surface) !important;
    border: 1px solid var(--border-2) !important;
    color: var(--text-2) !important;
    box-shadow: var(--shadow-sm) !important;
}
.stButton > button[kind="secondary"]:hover {
    background: rgba(255,255,255,0.9) !important;
    border-color: var(--accent) !important;
    color: var(--accent) !important;
}

/* ── Inputs & Textareas ── */
.stTextInput input, .stTextArea textarea, .stSelectbox select {
    font-family: 'Outfit', sans-serif !important;
    border-radius: 10px !important;
    border: 1.5px solid var(--border-2) !important;
    background: var(--surface) !important;
    color: var(--text) !important;
    backdrop-filter: blur(10px) !important;
    transition: border 0.15s, box-shadow 0.15s !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px var(--accent-light) !important;
    outline: none !important;
}
.stTextInput label, .stTextArea label { font-weight: 500 !important; color: var(--text-2) !important; font-size: 0.85rem !important; }

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    background: var(--surface) !important;
    border: 2px dashed rgba(79,70,229,0.25) !important;
    border-radius: var(--radius-lg) !important;
    transition: border-color 0.2s !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: rgba(79,70,229,0.5) !important;
    background: rgba(79,70,229,0.03) !important;
}
[data-testid="stFileUploaderDropInstructions"] { color: var(--text-3) !important; }

/* ── Expanders ── */
[data-testid="stExpander"] {
    background: var(--surface) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    box-shadow: var(--shadow-sm) !important;
    margin-bottom: 0.6rem !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    color: var(--text) !important;
    padding: 0.75rem 1rem !important;
}
[data-testid="stExpander"] summary:hover { background: var(--accent-light) !important; }

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: var(--surface) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1.25rem 1.5rem !important;
    box-shadow: var(--shadow-sm) !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.75rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    color: var(--text-3) !important;
}
[data-testid="stMetricValue"] {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: var(--text) !important;
    letter-spacing: -0.04em !important;
}

/* ── Alerts ── */
[data-testid="stAlert"] {
    border-radius: var(--radius) !important;
    border: none !important;
    backdrop-filter: blur(8px) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px !important;
    background: var(--surface-2) !important;
    border-radius: 10px !important;
    padding: 4px !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    color: var(--text-2) !important;
    transition: all 0.15s !important;
}
.stTabs [aria-selected="true"] {
    background: white !important;
    color: var(--accent) !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ── Divider ── */
hr { border-color: var(--border) !important; margin: 1.5rem 0 !important; }

/* ── Slider ── */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] { background: var(--accent) !important; }
[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stSliderThumb"] { background: var(--accent) !important; }

/* ══════════════════════════════
   FILE CARD
══════════════════════════════ */
.file-card {
    background: var(--surface);
    backdrop-filter: blur(14px) saturate(160%);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem 1.25rem;
    margin-bottom: 0.6rem;
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.2s, border-color 0.2s;
    display: flex;
    align-items: center;
    gap: 14px;
}
.file-card:hover { box-shadow: var(--shadow); border-color: var(--border-2); }
.file-icon {
    width: 40px; height: 40px; border-radius: 10px;
    background: var(--accent-light); display: flex;
    align-items: center; justify-content: center; font-size: 1.1rem; flex-shrink: 0;
}
.file-meta { flex: 1; min-width: 0; }
.file-name { font-weight: 600; font-size: 0.9rem; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.file-detail { font-size: 0.75rem; color: var(--text-3); margin-top: 2px; font-family: 'JetBrains Mono', monospace; }
.badge {
    display: inline-block; padding: 2px 8px; border-radius: 20px;
    font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
}
.badge-upload { background: rgba(5,150,105,0.1); color: #059669; }
.badge-scraped { background: rgba(79,70,229,0.1); color: #4f46e5; }

/* ══════════════════════════════
   CHAT
══════════════════════════════ */
.chat-container {
    background: var(--surface);
    backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: var(--shadow-lg);
}
.chat-topbar {
    background: rgba(255,255,255,0.85);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
    padding: 14px 20px;
    display: flex; align-items: center; gap: 12px;
}
.chat-topbar-avatar {
    width: 36px; height: 36px; border-radius: 10px;
    background: linear-gradient(135deg, #5b52f0, #8b5cf6);
    display: flex; align-items: center; justify-content: center; font-size: 1rem;
}
.chat-topbar-name { font-weight: 600; font-size: 0.92rem; color: var(--text); font-family: 'Outfit', sans-serif; }
.chat-topbar-status { font-size: 0.72rem; color: var(--success); font-family: 'Outfit', sans-serif; display: flex; align-items: center; gap: 4px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--success); display: inline-block; }
.chat-topbar-meta { margin-left: auto; font-size: 0.72rem; color: var(--text-3); font-family: 'JetBrains Mono', monospace; }

.chat-messages {
    padding: 20px;
    min-height: 360px;
    max-height: 480px;
    overflow-y: auto;
    display: flex; flex-direction: column; gap: 14px;
    background: linear-gradient(to bottom, rgba(248,248,252,0.8), rgba(242,243,247,0.8));
    scrollbar-width: thin;
    scrollbar-color: rgba(0,0,0,0.1) transparent;
}
.chat-messages::-webkit-scrollbar { width: 4px; }
.chat-messages::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.12); border-radius: 4px; }

.chat-ts-label {
    text-align: center; font-size: 0.68rem; color: var(--text-3);
    font-family: 'JetBrains Mono', monospace; margin: 4px 0;
}

/* User messages */
.msg-user { display: flex; justify-content: flex-end; gap: 8px; align-items: flex-end; }
.msg-user-bubble {
    background: linear-gradient(135deg, #5b52f0, #4338ca);
    color: #fff; padding: 10px 15px;
    border-radius: 18px 18px 4px 18px;
    font-size: 0.88rem; max-width: 70%;
    line-height: 1.55; font-family: 'Outfit', sans-serif;
    box-shadow: 0 3px 12px rgba(79,70,229,0.30);
}
.msg-user-av {
    width: 28px; height: 28px; border-radius: 50%;
    background: linear-gradient(135deg, #5b52f0, #4338ca);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.72rem; flex-shrink: 0; color: white; font-weight: 700;
}

/* Bot messages */
.msg-bot { display: flex; justify-content: flex-start; gap: 8px; align-items: flex-end; }
.msg-bot-av {
    width: 28px; height: 28px; border-radius: 50%;
    background: white; border: 1px solid var(--border-2);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; flex-shrink: 0;
    box-shadow: var(--shadow-sm);
}
.msg-bot-bubble {
    background: rgba(255,255,255,0.92);
    backdrop-filter: blur(10px);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 12px 15px;
    border-radius: 18px 18px 18px 4px;
    font-size: 0.87rem; max-width: 78%;
    line-height: 1.65; font-family: 'Outfit', sans-serif;
    box-shadow: var(--shadow-sm);
}
.msg-bot-bubble strong { color: var(--accent); }
.msg-bot-bubble ul, .msg-bot-bubble ol { margin: 6px 0 6px 16px; padding: 0; }
.msg-bot-bubble li { margin-bottom: 3px; color: var(--text-2); }
.msg-bot-bubble p { margin: 0 0 7px 0; color: var(--text); }
.msg-bot-bubble p:last-child { margin-bottom: 0; }

.chat-empty-state {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 280px; gap: 12px;
}
.chat-empty-icon {
    width: 56px; height: 56px; border-radius: 16px;
    background: var(--accent-light); display: flex;
    align-items: center; justify-content: center; font-size: 1.5rem;
}
.chat-empty-title { font-size: 0.95rem; font-weight: 600; color: var(--text-2); font-family: 'Outfit', sans-serif; }
.chat-empty-sub { font-size: 0.8rem; color: var(--text-3); font-family: 'Outfit', sans-serif; }

/* ══════════════════════════════
   SECTION HEADERS
══════════════════════════════ */
.section-label {
    font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; color: var(--text-3);
    margin-bottom: 0.75rem; margin-top: 1.5rem;
    font-family: 'Outfit', sans-serif;
}

/* ══════════════════════════════
   INFO BANNER
══════════════════════════════ */
.info-banner {
    background: var(--accent-light);
    border: 1px solid rgba(79,70,229,0.15);
    border-radius: var(--radius);
    padding: 12px 16px;
    font-size: 0.83rem;
    color: var(--accent);
    margin-bottom: 1rem;
    font-family: 'Outfit', sans-serif;
}

/* ══════════════════════════════
   TOOL CARD (Index Tools)
══════════════════════════════ */
.tool-card {
    background: var(--surface);
    backdrop-filter: blur(14px);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem 1.5rem;
    box-shadow: var(--shadow-sm);
    margin-bottom: 1rem;
}
.tool-card-title {
    font-size: 0.9rem; font-weight: 600;
    color: var(--text); margin-bottom: 4px;
    font-family: 'Outfit', sans-serif;
}
.tool-card-desc {
    font-size: 0.78rem; color: var(--text-3);
    margin-bottom: 1rem; font-family: 'Outfit', sans-serif;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
BASE_URL = st.sidebar.text_input("API Base URL", value="http://localhost:8000").rstrip("/")


def api(method, path, **kwargs):
    try:
        r = requests.request(method, BASE_URL + path, timeout=120, **kwargs)
        return (r.json(), None) if r.ok else (None, f"HTTP {r.status_code}: {r.text[:300]}")
    except requests.exceptions.ConnectionError:
        return None, "❌ Cannot connect to API. Is the FastAPI server running?"
    except Exception as e:
        return None, str(e)


def fmt_bytes(n):
    for u in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} GB"


def fmt_ts(ts):
    try:
        return datetime.fromtimestamp(ts).strftime("%b %d, %Y · %H:%M")
    except:
        return "—"


def now_str():
    return datetime.now().strftime("%H:%M")


def md_to_html(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    lines = text.split('\n')
    out, in_ol, in_ul = [], False, False
    ol_sub = re.compile(r'^\d+\.\s+')
    for line in lines:
        if re.match(r'^\d+\.\s', line):
            if not in_ol:
                out.append('<ol>')
                in_ol = True
            item = ol_sub.sub('', line)
            out.append(f"<li>{item}</li>")
        elif re.match(r'^[-•]\s', line):
            if not in_ul:
                out.append('<ul>')
                in_ul = True
            out.append(f"<li>{line[2:].strip()}</li>")
        else:
            if in_ol:
                out.append('</ol>')
                in_ol = False
            if in_ul:
                out.append('</ul>')
                in_ul = False
            out.append(f"<p>{line}</p>" if line.strip() else "")
    if in_ol:
        out.append('</ol>')
    if in_ul:
        out.append('</ul>')
    return ''.join(out)


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.markdown("""
<div style="padding: 0 0.5rem 1rem; display:flex; align-items:center; gap:10px;">
  <div style="width:34px;height:34px;background:linear-gradient(135deg,#5b52f0,#8b5cf6);border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:1rem;">✦</div>
  <div>
    <div style="font-weight:700;font-size:0.95rem;color:#1a1a2e;font-family:'Outfit',sans-serif;">Content Manager</div>
    <div style="font-size:0.7rem;color:#9898b8;font-family:'Outfit',sans-serif;">FAISS · GPT-4o · Docling</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown('<div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#9898b8;padding:0 0.5rem 0.4rem;font-family:Outfit,sans-serif;">Navigation</div>', unsafe_allow_html=True)

page = st.sidebar.radio(
    "nav",
    ["📋  Files", "⬆️  Upload", "💬  RAG Chat", "⚙️  Index Tools"],
    label_visibility="collapsed",
)

# Fetch live stats for sidebar
stats_side, _ = api("GET", "/rag/index/stats")
if stats_side:
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"""
    <div style="padding:0 0.5rem;">
      <div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#9898b8;margin-bottom:8px;font-family:Outfit,sans-serif;">Index Status</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <div style="background:rgba(79,70,229,0.08);border:1px solid rgba(79,70,229,0.15);border-radius:8px;padding:6px 10px;flex:1;">
          <div style="font-size:1.1rem;font-weight:700;color:#4f46e5;font-family:Outfit,sans-serif;">{stats_side.get('total_documents',0)}</div>
          <div style="font-size:0.65rem;color:#9898b8;font-family:Outfit,sans-serif;">DOCS</div>
        </div>
        <div style="background:rgba(79,70,229,0.08);border:1px solid rgba(79,70,229,0.15);border-radius:8px;padding:6px 10px;flex:1;">
          <div style="font-size:1.1rem;font-weight:700;color:#4f46e5;font-family:Outfit,sans-serif;">{stats_side.get('total_vectors',0)}</div>
          <div style="font-size:0.65rem;color:#9898b8;font-family:Outfit,sans-serif;">VECTORS</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# FILES PAGE
# ═══════════════════════════════════════════════════════════════════════════════
if page == "📋  Files":
    col_h, col_r = st.columns([5, 1])
    with col_h:
        st.markdown("""
        <div class="page-header">
          <div class="page-header-icon">📋</div>
          <div>
            <div class="page-header-title">All Files</div>
            <div class="page-header-sub">Browse, view and manage indexed documents</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with col_r:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("↺ Refresh", use_container_width=True):
            st.rerun()

    data, err = api("GET", "/files")
    if err:
        st.error(err)
        st.stop()

    files = data.get("files", [])
    if not files:
        st.markdown("""
        <div style="text-align:center;padding:3rem 1rem;background:rgba(255,255,255,0.6);border:1px solid rgba(0,0,0,0.07);border-radius:20px;backdrop-filter:blur(12px);">
          <div style="font-size:2.5rem;margin-bottom:12px;">📂</div>
          <div style="font-size:1rem;font-weight:600;color:#5a5a7a;font-family:Outfit,sans-serif;">No files yet</div>
          <div style="font-size:0.82rem;color:#9898b8;margin-top:4px;font-family:Outfit,sans-serif;">Upload a document or scrape a URL to get started</div>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    st.markdown(f'<div class="section-label">{len(files)} document{"s" if len(files)!=1 else ""} stored</div>', unsafe_allow_html=True)

    for f in files:
        fid      = f["file_id"]
        fname    = f.get("filename") or fid
        ftype    = f.get("type", "uploaded")
        size     = fmt_bytes(f.get("size_bytes", 0))
        modified = fmt_ts(f.get("last_modified", 0))
        has_json = f.get("has_json", False)
        pages    = f.get("page_count") or "—"
        blocks   = f.get("block_count") or "—"
        icon     = "🌐" if ftype == "scraped" else "📄"
        badge    = "badge-scraped" if ftype == "scraped" else "badge-upload"

        with st.expander(f"{icon}  {fname}"):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"""
                <div style="margin-bottom:10px;">
                  <span class="badge {badge}">{ftype}</span>
                  <span style="font-family:'JetBrains Mono',monospace;font-size:0.72rem;color:#9898b8;margin-left:8px;">{fid[:24]}…</span>
                </div>
                <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">
                  <div style="background:rgba(79,70,229,0.06);border-radius:8px;padding:8px 10px;">
                    <div style="font-size:0.65rem;color:#9898b8;text-transform:uppercase;letter-spacing:0.05em;font-family:Outfit,sans-serif;">Size</div>
                    <div style="font-size:0.88rem;font-weight:600;color:#1a1a2e;font-family:Outfit,sans-serif;">{size}</div>
                  </div>
                  <div style="background:rgba(79,70,229,0.06);border-radius:8px;padding:8px 10px;">
                    <div style="font-size:0.65rem;color:#9898b8;text-transform:uppercase;letter-spacing:0.05em;font-family:Outfit,sans-serif;">Pages</div>
                    <div style="font-size:0.88rem;font-weight:600;color:#1a1a2e;font-family:Outfit,sans-serif;">{pages}</div>
                  </div>
                  <div style="background:rgba(79,70,229,0.06);border-radius:8px;padding:8px 10px;">
                    <div style="font-size:0.65rem;color:#9898b8;text-transform:uppercase;letter-spacing:0.05em;font-family:Outfit,sans-serif;">Blocks</div>
                    <div style="font-size:0.88rem;font-weight:600;color:#1a1a2e;font-family:Outfit,sans-serif;">{blocks}</div>
                  </div>
                  <div style="background:rgba(79,70,229,0.06);border-radius:8px;padding:8px 10px;">
                    <div style="font-size:0.65rem;color:#9898b8;text-transform:uppercase;letter-spacing:0.05em;font-family:Outfit,sans-serif;">JSON</div>
                    <div style="font-size:0.88rem;font-weight:600;color:#059669;font-family:Outfit,sans-serif;">{'✓ Yes' if has_json else '—'}</div>
                  </div>
                </div>
                <div style="margin-top:8px;font-size:0.72rem;color:#9898b8;font-family:'JetBrains Mono',monospace;">{modified}</div>
                """, unsafe_allow_html=True)

            with col2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("👁 View Content", key=f"v_{fid}", use_container_width=True):
                    cd, ce = api("GET", f"/content/{fid}")
                    if ce:
                        st.error(ce)
                    else:
                        st.session_state[f"c_{fid}"] = cd
                if st.button("🗑 Delete", key=f"d_{fid}", type="secondary", use_container_width=True):
                    st.session_state[f"cd_{fid}"] = True

            if st.session_state.get(f"cd_{fid}"):
                st.warning(f"⚠️ Permanently delete **{fname}**? This cannot be undone.")
                b1, b2 = st.columns(2)
                if b1.button("Yes, delete", key=f"y_{fid}", type="primary"):
                    _, de = api("DELETE", f"/content/{fid}")
                    if de:
                        st.error(de)
                    else:
                        st.success("Deleted successfully.")
                        st.session_state.pop(f"cd_{fid}", None)
                        st.rerun()
                if b2.button("Cancel", key=f"n_{fid}"):
                    st.session_state.pop(f"cd_{fid}", None)
                    st.rerun()

            if f"c_{fid}" in st.session_state:
                cd = st.session_state[f"c_{fid}"]
                tab_labels = ["📝 Markdown", "🧩 Structured JSON"] if has_json else ["📝 Markdown"]
                tabs = st.tabs(tab_labels)
                with tabs[0]:
                    st.markdown(cd.get("content", "*(empty)*"))
                if has_json and len(tabs) > 1:
                    with tabs[1]:
                        jd, je = api("GET", f"/content/{fid}/json")
                        if je:
                            st.error(je)
                        else:
                            st.json(jd)
                if st.button("✕  Close", key=f"cl_{fid}"):
                    st.session_state.pop(f"c_{fid}", None)
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# UPLOAD PAGE (File Upload + URL Scrape in one popup-style dialog)
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "⬆️  Upload":
    st.markdown("""
    <div class="page-header">
      <div class="page-header-icon">⬆️</div>
      <div>
        <div class="page-header-title">Upload Content</div>
        <div class="page-header-sub">Upload a file or fetch from a URL — everything is saved as .md</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Upload method selector (popup-style) ──
    if "show_upload_popup" not in st.session_state:
        st.session_state["show_upload_popup"] = False
    if "upload_result" not in st.session_state:
        st.session_state["upload_result"] = None

    # Show last result if available
    if st.session_state["upload_result"]:
        res = st.session_state["upload_result"]
        st.markdown(f"""
        <div class="glass-card" style="border-left: 3px solid #059669;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
            <span style="font-size:1.3rem;">✅</span>
            <span style="font-weight:600;font-size:1rem;color:#1a1a2e;font-family:Outfit,sans-serif;">Successfully saved as</span>
          </div>
          <div style="background:rgba(79,70,229,0.06);border-radius:10px;padding:12px 16px;display:flex;align-items:center;gap:10px;">
            <span style="font-size:1.2rem;">📄</span>
            <span style="font-weight:700;font-size:1.05rem;color:#4f46e5;font-family:'JetBrains Mono',monospace;">{res['filename']}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if res.get("page_count") or res.get("block_count"):
            c1, c2 = st.columns(2)
            c1.metric("Pages", res.get("page_count", "—"))
            c2.metric("Blocks", res.get("block_count", "—"))

        with st.expander("📄 View Extracted Markdown"):
            st.markdown(res.get("content", "*(empty)*"))

        if st.button("Upload Another", type="secondary"):
            st.session_state["upload_result"] = None
            st.rerun()
        st.stop()

    # ── Main upload button ──
    st.markdown("<br>", unsafe_allow_html=True)
    col_btn = st.columns([1, 2, 1])
    with col_btn[1]:
        if st.button("+ Upload", type="primary", use_container_width=True):
            st.session_state["show_upload_popup"] = True
            st.rerun()

    if not st.session_state["show_upload_popup"]:
        st.markdown("""
        <div style="text-align:center;padding:3rem 1rem;background:rgba(255,255,255,0.6);border:1px solid rgba(0,0,0,0.07);border-radius:20px;backdrop-filter:blur(12px);margin-top:1rem;">
          <div style="font-size:2.5rem;margin-bottom:12px;">📂</div>
          <div style="font-size:1rem;font-weight:600;color:#5a5a7a;font-family:Outfit,sans-serif;">Click Upload to add content</div>
          <div style="font-size:0.82rem;color:#9898b8;margin-top:4px;font-family:Outfit,sans-serif;">Upload a file or paste a URL to scrape — output is always a .md file</div>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    # ── Popup content ──
    st.markdown("""
    <div class="glass-card">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
        <span style="font-weight:700;font-size:1.05rem;color:#1a1a2e;font-family:Outfit,sans-serif;">Add Content</span>
      </div>
      <div style="font-size:0.8rem;color:#9898b8;font-family:Outfit,sans-serif;margin-bottom:8px;">Choose how you want to add content</div>
    </div>
    """, unsafe_allow_html=True)

    tab_file, tab_url = st.tabs(["📁 File Upload", "🌐 URL"])

    # ── File Upload tab ──
    with tab_file:
        st.markdown("""
        <div class="info-banner">
          ✦ &nbsp; Supported: <strong>PDF</strong> · <strong>TXT</strong> · <strong>MD</strong> · <strong>PNG</strong> · <strong>JPG</strong> · <strong>WEBP</strong> · <strong>BMP</strong> · <strong>TIFF</strong>
        </div>
        """, unsafe_allow_html=True)

        uploaded = st.file_uploader(
            "Drop your file here",
            type=["pdf", "txt", "md", "png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif"],
            label_visibility="collapsed",
        )

        if uploaded:
            st.markdown(f"""
            <div class="glass-card-sm" style="display:flex;align-items:center;gap:12px;margin:0.75rem 0;">
              <div style="width:38px;height:38px;background:rgba(5,150,105,0.1);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.1rem;">📎</div>
              <div>
                <div style="font-weight:600;font-size:0.9rem;color:#1a1a2e;font-family:Outfit,sans-serif;">{uploaded.name}</div>
                <div style="font-size:0.75rem;color:#9898b8;font-family:'JetBrains Mono',monospace;">{fmt_bytes(uploaded.size)}</div>
              </div>
              <div style="margin-left:auto;"><span class="badge badge-upload">Ready</span></div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("⬆️  Upload & Convert to .md", type="primary", key="upload_file_btn"):
                with st.spinner("Processing... Converting to markdown in background"):
                    data, err = api("POST", "/upload", files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
                if err:
                    st.error(err)
                else:
                    st.session_state["upload_result"] = data
                    st.session_state["show_upload_popup"] = False
                    st.rerun()

    # ── URL tab ──
    with tab_url:
        st.markdown("""
        <div class="info-banner">
          ✦ &nbsp; Paste a URL below and click <strong>Fetch Info</strong> to scrape the page and convert it to markdown
        </div>
        """, unsafe_allow_html=True)

        url_col, btn_col = st.columns([4, 1])
        with url_col:
            url = st.text_input(
                "URL",
                placeholder="https://example.com/page",
                label_visibility="collapsed",
                key="scrape_url_input",
            )
        with btn_col:
            fetch_clicked = st.button("Fetch Info", type="primary", use_container_width=True, key="fetch_info_btn")

        if fetch_clicked and url.strip():
            with st.spinner("Fetching & converting to markdown..."):
                data, err = api("POST", "/scrape", json={"url": url.strip()})
            if err:
                st.error(err)
            else:
                st.session_state["upload_result"] = data
                st.session_state["show_upload_popup"] = False
                st.rerun()
        elif fetch_clicked and not url.strip():
            st.warning("Please enter a URL first.")

    # Cancel button
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Cancel", type="secondary", use_container_width=True):
        st.session_state["show_upload_popup"] = False
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# RAG CHAT PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "💬  RAG Chat":

    if "chat_msgs" not in st.session_state:
        st.session_state["chat_msgs"] = []
    if "chat_topk" not in st.session_state:
        st.session_state["chat_topk"] = 5

    # Header row
    col_h, col_c = st.columns([5, 1])
    with col_h:
        st.markdown("""
        <div class="page-header">
          <div class="page-header-icon">💬</div>
          <div>
            <div class="page-header-title">RAG Chat</div>
            <div class="page-header-sub">Ask questions — answers grounded in your indexed documents</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with col_c:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("🗑 Clear", use_container_width=True):
            st.session_state["chat_msgs"] = []
            st.rerun()

    # Stats
    stats, _ = api("GET", "/rag/index/stats")
    if stats:
        n_docs = stats.get("total_documents", 0)
        n_vecs = stats.get("total_vectors", 0)
        topk   = st.session_state["chat_topk"]
        st.markdown(f"""
        <div class="stat-row">
          <span class="stat-chip"><span class="dot"></span> <strong>{n_docs}</strong> documents indexed</span>
          <span class="stat-chip"><span class="dot"></span> <strong>{n_vecs}</strong> vectors</span>
          <span class="stat-chip">top_k = <strong>{topk}</strong></span>
        </div>
        """, unsafe_allow_html=True)

    # Build messages HTML
    msgs = st.session_state["chat_msgs"]
    if not msgs:
        body_html = """
        <div class="chat-empty-state">
          <div class="chat-empty-icon">💬</div>
          <div class="chat-empty-title">Start a conversation</div>
          <div class="chat-empty-sub">Ask anything about your indexed documents</div>
        </div>"""
    else:
        body_html = ""
        for m in msgs:
            ts = m.get("ts", "")
            body_html += f'<div class="chat-ts-label">{ts}</div>'
            if m["role"] == "user":
                body_html += f"""
                <div class="msg-user">
                  <div class="msg-user-bubble">{m['content']}</div>
                  <div class="msg-user-av">U</div>
                </div>"""
            else:
                content_html = md_to_html(m["content"])
                body_html += f"""
                <div class="msg-bot">
                  <div class="msg-bot-av">✦</div>
                  <div class="msg-bot-bubble">{content_html}</div>
                </div>"""

    st.markdown(f"""
    <div class="chat-container">
      <div class="chat-topbar">
        <div class="chat-topbar-avatar">✦</div>
        <div>
          <div class="chat-topbar-name">Document Assistant</div>
          <div class="chat-topbar-status"><span class="status-dot"></span> Online · GPT-4o</div>
        </div>
        <div class="chat-topbar-meta">FAISS RAG</div>
      </div>
      <div class="chat-messages">{body_html}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Input
    ci, cs = st.columns([5, 1])
    with ci:
        query = st.text_input(
            "message",
            placeholder="Ask something about your documents…",
            label_visibility="collapsed",
            key="chat_inp",
        )
    with cs:
        send = st.button("Send ➤", type="primary", use_container_width=True)

    with st.expander("⚙️  Settings"):
        st.session_state["chat_topk"] = st.slider(
            "Chunks to retrieve (top_k)", 1, 20, st.session_state["chat_topk"],
            help="Higher values retrieve more context but increase cost and latency."
        )

    if send and query.strip():
        st.session_state["chat_msgs"].append({
            "role": "user", "content": query.strip(), "ts": now_str()
        })
        with st.spinner("Searching and generating…"):
            data, err = api(
                "POST", "/rag/query",
                json={"query": query.strip(), "top_k": st.session_state["chat_topk"]},
            )
        answer = f"⚠️ Error: {err}" if err else data.get("answer", "No answer returned.")
        st.session_state["chat_msgs"].append({
            "role": "assistant", "content": answer, "ts": now_str()
        })
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# INDEX TOOLS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "⚙️  Index Tools":
    col_h, col_r = st.columns([5, 1])
    with col_h:
        st.markdown("""
        <div class="page-header">
          <div class="page-header-icon">⚙️</div>
          <div>
            <div class="page-header-title">Index Tools</div>
            <div class="page-header-sub">Manage the FAISS vector index and API health</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with col_r:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("↺ Refresh", use_container_width=True):
            st.rerun()

    # Stats
    stats, err = api("GET", "/rag/index/stats")
    if err:
        st.error(err)
    else:
        c1, c2 = st.columns(2)
        c1.metric("Indexed Documents", stats.get("total_documents", 0))
        c2.metric("Total Vectors", stats.get("total_vectors", 0))
        ids = stats.get("indexed_file_ids", [])
        if ids:
            with st.expander(f"📋  Indexed File IDs  ({len(ids)})"):
                for fid in ids:
                    st.code(fid, language=None)

    st.markdown("---")

    # Rebuild
    st.markdown("""
    <div class="tool-card">
      <div class="tool-card-title">🔨 Rebuild Full Index</div>
      <div class="tool-card-desc">Re-embeds all stored documents from scratch. This may take several minutes and will use OpenAI API credits.</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🔨  Rebuild Index", type="primary"):
        with st.spinner("Rebuilding index from scratch…"):
            data, err = api("POST", "/rag/index/rebuild")
        if err:
            st.error(err)
        else:
            st.success(data.get("message", "Done!"))
            st.metric("Total Vectors After Rebuild", data.get("total_vectors", "—"))

    st.markdown("---")

    # Remove document
    st.markdown("""
    <div class="tool-card">
      <div class="tool-card-title">🗑 Remove Document from Index</div>
      <div class="tool-card-desc">Removes all vectors for a specific file without deleting the document itself.</div>
    </div>
    """, unsafe_allow_html=True)
    rid = st.text_input("File ID", placeholder="Paste a file_id here…", key="rid_input")
    if st.button("Remove from Index", disabled=not rid.strip()):
        data, err = api("DELETE", f"/rag/index/{rid.strip()}")
        if err:
            st.error(err)
        else:
            st.success(data.get("message", "Removed from index."))

    st.markdown("---")

    # API Health
    st.markdown("""
    <div class="tool-card">
      <div class="tool-card-title">🏓 API Health Check</div>
      <div class="tool-card-desc">Verify that the FastAPI backend is reachable and responding.</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🏓  Ping API"):
        data, err = api("GET", "/")
        if err:
            st.error(err)
        else:
            st.success(f"✅  {data.get('message', 'API is running')}")