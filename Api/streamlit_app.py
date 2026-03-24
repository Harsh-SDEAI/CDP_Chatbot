import streamlit as st
import requests
import re
from datetime import datetime

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CDP Content Manager",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Dark Grey Theme CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg:             #1e1e2e;
    --bg-2:           #2a2a3c;
    --surface:        rgba(42,42,60,0.80);
    --surface-2:      rgba(255,255,255,0.03);
    --surface-3:      rgba(255,255,255,0.06);
    --border:         rgba(255,255,255,0.08);
    --border-2:       rgba(255,255,255,0.12);
    --border-3:       rgba(255,255,255,0.18);
    --text:           #e8e8ef;
    --text-2:         #b0b0c0;
    --text-3:         #7a7a90;
    --accent:         #b0b0c0;
    --accent-2:       #d0d0dd;
    --accent-bg:      rgba(255,255,255,0.04);
    --accent-bg-2:    rgba(255,255,255,0.08);
    --green:          #4eca7a;
    --green-bg:       rgba(78,202,122,0.12);
    --red:            #f06060;
    --red-bg:         rgba(240,96,96,0.10);
    --orange:         #e8a84a;
    --radius:         10px;
    --radius-lg:      14px;
    --radius-xl:      18px;
    --shadow-sm:      0 1px 2px rgba(0,0,0,0.20);
    --shadow:         0 2px 8px rgba(0,0,0,0.30);
    --shadow-lg:      0 4px 16px rgba(0,0,0,0.40);
}

/* ── Base ── */
html, body, [class*="css"], .stApp, .main {
    font-family: 'Inter', -apple-system, sans-serif !important;
    background: var(--bg) !important;
    color: var(--text) !important;
}
.main .block-container {
    padding: 2rem 2.5rem 4rem !important;
    max-width: 1100px !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.12); border-radius: 8px; }
::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.2); }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: var(--bg-2) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 1rem !important; }
[data-testid="stSidebar"] .stRadio > div { gap: 2px !important; }
[data-testid="stSidebar"] .stRadio label {
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    padding: 9px 14px !important;
    border-radius: 8px !important;
    transition: all 0.15s !important;
    color: var(--text-2) !important;
    border: 1px solid transparent !important;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: var(--surface-3) !important;
    color: var(--text) !important;
}
[data-testid="stSidebar"] .stRadio label[data-checked="true"],
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:has(input:checked) {
    background: var(--accent-bg-2) !important;
    color: var(--text) !important;
    font-weight: 600 !important;
    border-color: var(--border) !important;
}
[data-testid="stSidebar"] input {
    background: var(--bg) !important;
    border: 1px solid var(--border-2) !important;
    border-radius: 8px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.75rem !important;
    color: var(--text) !important;
}
[data-testid="stSidebar"] hr {
    border-color: var(--border) !important;
    margin: 0.75rem 0 !important;
}

/* ── Typography ── */
h1 {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
    color: var(--text) !important;
    line-height: 1.2 !important;
}
h2 { font-size: 1.1rem !important; font-weight: 600 !important; color: var(--text) !important; }
h3 { font-size: 0.95rem !important; font-weight: 600 !important; color: var(--text) !important; }
p, li { color: var(--text-2) !important; }

/* ── Buttons ── */
.stButton > button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.84rem !important;
    border-radius: 8px !important;
    transition: all 0.15s ease !important;
    letter-spacing: -0.01em !important;
}
.stButton > button[kind="primary"] {
    background: #3a3a50 !important;
    border: 1px solid #4a4a62 !important;
    color: #e8e8ef !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.20) !important;
}
.stButton > button[kind="primary"]:hover {
    background: #4a4a62 !important;
    border-color: #5a5a72 !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.30) !important;
    transform: translateY(-0.5px) !important;
}
.stButton > button[kind="primary"]:active { transform: translateY(0) !important; }
.stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid var(--border-2) !important;
    color: var(--text-2) !important;
}
.stButton > button[kind="secondary"]:hover {
    background: var(--surface-3) !important;
    border-color: var(--border-3) !important;
    color: var(--text) !important;
}

/* ── Inputs ── */
.stTextInput input, .stTextArea textarea, .stSelectbox select {
    font-family: 'Inter', sans-serif !important;
    border-radius: 8px !important;
    border: 1px solid var(--border-2) !important;
    background: var(--bg-2) !important;
    color: var(--text) !important;
    transition: border 0.15s, box-shadow 0.15s !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--text-3) !important;
    box-shadow: 0 0 0 2px rgba(0,0,0,0.04) !important;
    outline: none !important;
}
.stTextInput input::placeholder, .stTextArea textarea::placeholder { color: var(--text-3) !important; }
.stTextInput label, .stTextArea label { font-weight: 500 !important; color: var(--text-3) !important; font-size: 0.82rem !important; }

/* ── File Uploader ── */
[data-testid="stFileUploader"] {
    background: var(--bg-2) !important;
    border: 2px dashed var(--border-2) !important;
    border-radius: var(--radius-lg) !important;
    transition: all 0.15s !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--text-3) !important;
    background: var(--surface-2) !important;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background: var(--bg-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    margin-bottom: 6px !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-sm) !important;
}
[data-testid="stExpander"] summary {
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    color: var(--text) !important;
    padding: 0.7rem 1rem !important;
}
[data-testid="stExpander"] summary:hover { background: var(--surface-2) !important; }
[data-testid="stExpander"] [data-testid="stExpanderDetails"] { border-top: 1px solid var(--border) !important; }

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: var(--bg-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1.25rem 1.5rem !important;
    box-shadow: var(--shadow-sm) !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.68rem !important; font-weight: 600 !important;
    text-transform: uppercase !important; letter-spacing: 0.08em !important;
    color: var(--text-3) !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.7rem !important; font-weight: 800 !important;
    color: var(--text) !important; letter-spacing: -0.04em !important;
}

/* ── Alerts ── */
[data-testid="stAlert"] { border-radius: var(--radius) !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px !important;
    background: var(--surface-2) !important;
    border-radius: 8px !important;
    padding: 3px !important;
    border: 1px solid var(--border) !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 6px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.84rem !important;
    color: var(--text-3) !important;
    transition: all 0.15s !important;
}
.stTabs [aria-selected="true"] {
    background: var(--bg-2) !important;
    color: var(--text) !important;
    font-weight: 600 !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ── Divider ── */
hr { border-color: var(--border) !important; margin: 1.5rem 0 !important; }

/* ── Slider ── */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] { background: #5a5a72 !important; }

/* ══ Custom Components ══ */

.page-hero {
    padding: 0 0 1.25rem;
    margin-bottom: 1.25rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 14px;
}
.page-hero-icon {
    width: 44px; height: 44px;
    background: #3a3a50;
    border: 1px solid #4a4a62;
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem;
}
.page-hero-text h1 {
    margin: 0 !important; padding: 0 !important;
    font-size: 1.4rem !important;
}
.page-hero-sub {
    font-size: 0.82rem; color: var(--text-3);
    margin-top: 2px; font-family: 'Inter', sans-serif;
}

.stat-pills {
    display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 1.25rem;
}
.stat-pill {
    display: inline-flex; align-items: center; gap: 7px;
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: 100px;
    padding: 5px 12px 5px 9px;
    font-size: 0.76rem;
    color: var(--text-2);
    font-family: 'Inter', sans-serif;
    box-shadow: var(--shadow-sm);
}
.stat-pill-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--text-3);
}
.stat-pill strong { color: var(--text); font-weight: 700; }

.card {
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1.25rem 1.5rem;
    margin-bottom: 0.75rem;
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.15s;
}
.card:hover { box-shadow: var(--shadow); }
.card-accent { border-left: 3px solid var(--text-3); }
.card-success { border-left: 3px solid var(--green); }

.file-row {
    display: flex;
    align-items: center;
    gap: 12px;
}
.file-icon-box {
    width: 40px; height: 40px;
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.1rem;
    flex-shrink: 0;
}
.file-icon-upload { background: var(--green-bg); }
.file-icon-scraped { background: var(--surface-3); }
.file-info { flex: 1; min-width: 0; }
.file-name {
    font-weight: 600; font-size: 0.9rem;
    color: var(--text);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    font-family: 'Inter', sans-serif;
}
.file-detail {
    font-size: 0.72rem; color: var(--text-3);
    margin-top: 2px; font-family: 'JetBrains Mono', monospace;
}
.badge {
    display: inline-block; padding: 3px 9px; border-radius: 100px;
    font-size: 0.62rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em;
}
.badge-upload { background: var(--green-bg); color: var(--green); }
.badge-scraped { background: var(--surface-3); color: var(--text-2); }

.mini-stat-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    margin: 8px 0;
}
.mini-stat {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 7px 9px;
}
.mini-stat-label {
    font-size: 0.58rem; color: var(--text-3);
    text-transform: uppercase; letter-spacing: 0.06em;
    font-family: 'Inter', sans-serif; font-weight: 600;
}
.mini-stat-value {
    font-size: 0.88rem; font-weight: 700;
    color: var(--text); font-family: 'Inter', sans-serif;
    margin-top: 1px;
}

.section-label {
    font-size: 0.66rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.1em;
    color: var(--text-3); margin-bottom: 0.75rem;
    font-family: 'Inter', sans-serif;
}

.info-pill {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 9px 14px;
    font-size: 0.8rem;
    color: var(--text-2);
    margin-bottom: 1rem;
    font-family: 'Inter', sans-serif;
}
.info-pill strong { color: var(--text); }

.tool-card {
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem 1.5rem;
    margin-bottom: 0.75rem;
    box-shadow: var(--shadow-sm);
}
.tool-card-title {
    font-size: 0.9rem; font-weight: 600;
    color: var(--text); margin-bottom: 4px;
    font-family: 'Inter', sans-serif;
}
.tool-card-desc {
    font-size: 0.78rem; color: var(--text-3);
    margin-bottom: 1rem; font-family: 'Inter', sans-serif;
    line-height: 1.5;
}

/* ══ Floating Chat Widget ══ */
.chat-fab {
    position: fixed; bottom: 28px; right: 28px; z-index: 9999;
    width: 56px; height: 56px; border-radius: 50%;
    background: #3a3a50; border: 2px solid #4a4a62;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    font-size: 1.4rem; color: #e8e8ef;
    transition: transform 0.2s, box-shadow 0.2s;
}
.chat-fab:hover { transform: scale(1.08); box-shadow: 0 6px 28px rgba(0,0,0,0.6); }

.chat-widget {
    position: fixed; bottom: 96px; right: 28px; z-index: 9998;
    width: 370px; max-height: 520px;
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    border-radius: 16px;
    box-shadow: 0 8px 40px rgba(0,0,0,0.55);
    display: flex; flex-direction: column;
    overflow: hidden;
}

.cw-header {
    background: var(--bg);
    border-bottom: 1px solid var(--border);
    padding: 12px 16px;
    display: flex; align-items: center; gap: 10px;
}
.cw-avatar {
    width: 32px; height: 32px; border-radius: 8px;
    background: #3a3a50;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; color: #b0b0c0; font-weight: 700;
}
.cw-header-name { font-weight: 600; font-size: 0.85rem; color: var(--text); }
.cw-header-status {
    font-size: 0.65rem; color: var(--green);
    display: flex; align-items: center; gap: 4px;
}
.cw-header-status::before {
    content: ''; width: 5px; height: 5px;
    border-radius: 50%; background: var(--green); display: inline-block;
}

.cw-messages {
    flex: 1; padding: 14px;
    overflow-y: auto;
    display: flex; flex-direction: column; gap: 8px;
    background: var(--bg);
    max-height: 360px; min-height: 200px;
}

.cw-ts { text-align: center; font-size: 0.58rem; color: var(--text-3); font-family: 'JetBrains Mono', monospace; margin: 2px 0; }

.cw-msg-user { display: flex; justify-content: flex-end; gap: 6px; align-items: flex-end; }
.cw-msg-user-bubble {
    background: #3a3a50; color: #e8e8ef;
    padding: 8px 12px; border-radius: 12px 12px 4px 12px;
    font-size: 0.8rem; max-width: 75%; line-height: 1.5;
}

.cw-msg-bot { display: flex; justify-content: flex-start; gap: 6px; align-items: flex-end; }
.cw-msg-bot-av {
    width: 22px; height: 22px; border-radius: 50%;
    background: var(--surface-3); border: 1px solid var(--border);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.6rem; flex-shrink: 0; color: var(--text-2);
}
.cw-msg-bot-bubble {
    background: var(--bg-2); border: 1px solid var(--border);
    color: var(--text); padding: 8px 12px;
    border-radius: 12px 12px 12px 4px;
    font-size: 0.8rem; max-width: 80%; line-height: 1.5;
    box-shadow: var(--shadow-sm);
}
.cw-msg-bot-bubble strong { color: var(--text); }
.cw-msg-bot-bubble ul, .cw-msg-bot-bubble ol { margin: 4px 0 4px 14px; padding: 0; }
.cw-msg-bot-bubble li { margin-bottom: 1px; color: var(--text-2); font-size: 0.78rem; }
.cw-msg-bot-bubble p { margin: 0 0 4px 0; color: var(--text); }
.cw-msg-bot-bubble p:last-child { margin-bottom: 0; }

.cw-empty {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 200px; gap: 8px;
}
.cw-empty-icon { font-size: 1.8rem; }
.cw-empty-title { font-size: 0.85rem; font-weight: 600; color: var(--text-2); }
.cw-empty-sub { font-size: 0.72rem; color: var(--text-3); }

/* ── Hide the floating chat streamlit container chrome ── */
div[data-testid="stVerticalBlock"]:has(> .floating-chat-anchor) {
    position: fixed !important; bottom: 96px; right: 28px; z-index: 9998;
    width: 370px !important;
}

/* ══ Empty State ══ */
.empty-state {
    text-align: center;
    padding: 3.5rem 2rem;
    background: var(--bg-2);
    border: 1px dashed var(--border-2);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-sm);
}
.empty-icon {
    width: 56px; height: 56px; border-radius: 14px;
    background: var(--surface-3); border: 1px solid var(--border);
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 1.4rem; margin-bottom: 14px;
}
.empty-title { font-size: 1rem; font-weight: 600; color: var(--text-2); font-family: 'Inter', sans-serif; }
.empty-sub { font-size: 0.8rem; color: var(--text-3); margin-top: 4px; font-family: 'Inter', sans-serif; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
BASE_URL = st.sidebar.text_input("API Base URL", value="http://localhost:8000").rstrip("/")


def api(method, path, **kwargs):
    try:
        r = requests.request(method, BASE_URL + path, timeout=120, **kwargs)
        return (r.json(), None) if r.ok else (None, f"HTTP {r.status_code}: {r.text[:300]}")
    except requests.exceptions.ConnectionError:
        return None, "Cannot connect to API. Is the FastAPI server running?"
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
        return datetime.fromtimestamp(ts).strftime("%b %d, %Y  %H:%M")
    except Exception:
        return ""


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
        elif re.match(r'^[-]\s', line):
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
<div style="padding:0.25rem 0.5rem 1.25rem;display:flex;align-items:center;gap:11px;">
  <div style="width:36px;height:36px;background:#3a3a50;border-radius:10px;display:flex;align-items:center;justify-content:center;">
    <span style="color:#b0b0c0;font-weight:700;font-size:0.85rem;font-family:Inter,sans-serif;">C</span>
  </div>
  <div>
    <div style="font-weight:700;font-size:0.95rem;color:#e8e8ef;font-family:Inter,sans-serif;letter-spacing:-0.02em;">Content Manager</div>
    <div style="font-size:0.66rem;color:#7a7a90;font-family:'JetBrains Mono',monospace;">FAISS &middot; GPT-4o &middot; Docling</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown('<div style="font-size:0.6rem;font-weight:600;text-transform:uppercase;letter-spacing:0.1em;color:#7a7a90;padding:0 0.5rem 0.4rem;font-family:Inter,sans-serif;">Navigation</div>', unsafe_allow_html=True)

page = st.sidebar.radio(
    "nav",
    ["Files", "Upload", "Index Tools"],
    label_visibility="collapsed",
)

# Sidebar stats
stats_side, _ = api("GET", "/rag/index/stats")
if stats_side:
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"""
    <div style="padding:0 0.5rem;">
      <div style="font-size:0.6rem;font-weight:600;text-transform:uppercase;letter-spacing:0.1em;color:#7a7a90;margin-bottom:8px;font-family:Inter,sans-serif;">Index Status</div>
      <div style="display:flex;gap:6px;">
        <div style="flex:1;background:#1e1e2e;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:8px 10px;">
          <div style="font-size:1.3rem;font-weight:800;color:#e8e8ef;font-family:Inter,sans-serif;letter-spacing:-0.03em;">{stats_side.get('total_documents',0)}</div>
          <div style="font-size:0.58rem;color:#7a7a90;font-family:Inter,sans-serif;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;">Docs</div>
        </div>
        <div style="flex:1;background:#1e1e2e;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:8px 10px;">
          <div style="font-size:1.3rem;font-weight:800;color:#e8e8ef;font-family:Inter,sans-serif;letter-spacing:-0.03em;">{stats_side.get('total_vectors',0)}</div>
          <div style="font-size:0.58rem;color:#7a7a90;font-family:Inter,sans-serif;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;">Vectors</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# FILES PAGE
# ═══════════════════════════════════════════════════════════════════════════════
if page == "Files":
    col_h, col_r = st.columns([5, 1])
    with col_h:
        st.markdown("""
        <div class="page-hero">
          <div class="page-hero-icon">&#128196;</div>
          <div class="page-hero-text">
            <h1>All Files</h1>
            <div class="page-hero-sub">Browse, view and manage your indexed documents</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with col_r:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Refresh", use_container_width=True):
            st.rerun()

    data, err = api("GET", "/files")
    if err:
        st.error(err)
        st.stop()

    files = data.get("files", [])
    if not files:
        st.markdown("""
        <div class="empty-state">
          <div class="empty-icon">&#128194;</div>
          <div class="empty-title">No files yet</div>
          <div class="empty-sub">Upload a document or scrape a URL to get started</div>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    st.markdown(f'<div class="section-label">{len(files)} document{"s" if len(files)!=1 else ""} stored</div>', unsafe_allow_html=True)

    for f in files:
        fid      = f["file_id"]
        fname    = f.get("filename") or f"{fid}.md"
        # Always display as .md
        if not fname.endswith(".md"):
            from pathlib import PurePosixPath
            fname = PurePosixPath(fname).stem + ".md"
        ftype    = f.get("type", "uploaded")
        size     = fmt_bytes(f.get("size_bytes", 0))
        modified = fmt_ts(f.get("last_modified", 0))
        has_json = f.get("has_json", False)
        pages    = f.get("page_count") or ""
        blocks   = f.get("block_count") or ""
        is_scraped = ftype == "scraped"
        icon_class = "file-icon-scraped" if is_scraped else "file-icon-upload"
        icon_char  = "&#127760;" if is_scraped else "&#128196;"
        badge_class = "badge-scraped" if is_scraped else "badge-upload"

        with st.expander(f"{'[WEB]' if is_scraped else '[FILE]'}  {fname}"):
            st.markdown(f"""
            <div class="file-row" style="margin-bottom:8px;">
              <div class="file-icon-box {icon_class}">{icon_char}</div>
              <div class="file-info">
                <div class="file-name">{fname}</div>
                <div class="file-detail">{modified}</div>
              </div>
              <span class="badge {badge_class}">{ftype}</span>
            </div>
            <div class="mini-stat-grid">
              <div class="mini-stat"><div class="mini-stat-label">Size</div><div class="mini-stat-value">{size}</div></div>
              <div class="mini-stat"><div class="mini-stat-label">Pages</div><div class="mini-stat-value">{pages}</div></div>
              <div class="mini-stat"><div class="mini-stat-label">Blocks</div><div class="mini-stat-value">{blocks}</div></div>
              <div class="mini-stat"><div class="mini-stat-label">JSON</div><div class="mini-stat-value" style="color:{'var(--green)' if has_json else 'var(--text-3)'};">{'Yes' if has_json else ''}</div></div>
            </div>
            """, unsafe_allow_html=True)

            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("View Content", key=f"v_{fid}", use_container_width=True):
                    cd, ce = api("GET", f"/content/{fid}")
                    if ce:
                        st.error(ce)
                    else:
                        st.session_state[f"c_{fid}"] = cd
            with bc2:
                if st.button("Delete", key=f"d_{fid}", type="secondary", use_container_width=True):
                    st.session_state[f"cd_{fid}"] = True

            if st.session_state.get(f"cd_{fid}"):
                st.warning(f"Permanently delete **{fname}**? This cannot be undone.")
                b1, b2 = st.columns(2)
                if b1.button("Yes, delete", key=f"y_{fid}", type="primary"):
                    _, de = api("DELETE", f"/content/{fid}")
                    if de:
                        st.error(de)
                    else:
                        st.success("Deleted.")
                        st.session_state.pop(f"cd_{fid}", None)
                        st.rerun()
                if b2.button("Cancel", key=f"n_{fid}"):
                    st.session_state.pop(f"cd_{fid}", None)
                    st.rerun()

            if f"c_{fid}" in st.session_state:
                cd = st.session_state[f"c_{fid}"]
                tab_labels = ["Markdown", "Structured JSON"] if has_json else ["Markdown"]
                tabs = st.tabs(tab_labels)
                with tabs[0]:
                    # Toggle between view and edit mode
                    editing = st.session_state.get(f"edit_{fid}", False)
                    if not editing:
                        st.markdown(cd.get("content", "*(empty)*"))
                        if st.button("Edit", key=f"e_{fid}", use_container_width=True):
                            st.session_state[f"edit_{fid}"] = True
                            st.rerun()
                    else:
                        edited_md = st.text_area(
                            "Edit Markdown",
                            value=cd.get("content", ""),
                            height=400,
                            key=f"ta_{fid}",
                        )
                        save_col, cancel_col = st.columns(2)
                        with save_col:
                            if st.button("Save", key=f"s_{fid}", type="primary", use_container_width=True):
                                save_resp, save_err = api("PUT", "/content", json={"file_id": fid, "content": edited_md})
                                if save_err:
                                    st.error(save_err)
                                else:
                                    st.success("Saved & re-indexed!")
                                    st.session_state[f"c_{fid}"]["content"] = edited_md
                                    st.session_state.pop(f"edit_{fid}", None)
                                    st.rerun()
                        with cancel_col:
                            if st.button("Cancel", key=f"ce_{fid}", use_container_width=True):
                                st.session_state.pop(f"edit_{fid}", None)
                                st.rerun()
                if has_json and len(tabs) > 1:
                    with tabs[1]:
                        jd, je = api("GET", f"/content/{fid}/json")
                        if je:
                            st.error(je)
                        else:
                            st.json(jd)
                if st.button("Close", key=f"cl_{fid}"):
                    st.session_state.pop(f"c_{fid}", None)
                    st.session_state.pop(f"edit_{fid}", None)
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# UPLOAD PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Upload":
    st.markdown("""
    <div class="page-hero">
      <div class="page-hero-icon">&#11014;</div>
      <div class="page-hero-text">
        <h1>Upload Content</h1>
        <div class="page-hero-sub">Upload a file or fetch from a URL &mdash; everything is saved as .md</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Session state init ──
    if "upload_mode" not in st.session_state:
        st.session_state["upload_mode"] = None          # None | "file" | "url"
    if "upload_result" not in st.session_state:
        st.session_state["upload_result"] = None

    # ── Result view (after successful upload/scrape) ──
    if st.session_state["upload_result"]:
        res = st.session_state["upload_result"]
        md_name = res.get("filename", "output.md")
        source_type = "Scraped" if res.get("source_url") or res.get("url") else "Uploaded"
        source_url  = res.get("source_url") or res.get("url") or ""

        st.markdown(f"""
        <div class="card card-success">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
            <span style="font-size:1.2rem;">&#9989;</span>
            <span style="font-weight:700;font-size:1rem;color:var(--text);">Successfully converted to Markdown</span>
          </div>
          <div style="background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:14px 18px;display:flex;align-items:center;gap:12px;">
            <span style="font-size:1.3rem;">&#128196;</span>
            <div>
              <div style="font-weight:700;font-size:1rem;color:var(--text);font-family:'JetBrains Mono',monospace;">{md_name}</div>
              <div style="font-size:0.72rem;color:var(--text-3);margin-top:2px;">{source_type}{(' &middot; ' + source_url) if source_url else ''}</div>
            </div>
            <span class="badge {'badge-scraped' if source_url else 'badge-upload'}" style="margin-left:auto;">{source_type}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if res.get("page_count") or res.get("block_count"):
            c1, c2 = st.columns(2)
            c1.metric("Pages", res.get("page_count", ""))
            c2.metric("Blocks", res.get("block_count", ""))

        with st.expander("View Extracted Markdown"):
            st.markdown(res.get("content", "*(empty)*"))

        if st.button("Upload Another", type="secondary"):
            st.session_state["upload_result"] = None
            st.session_state["upload_mode"] = None
            st.rerun()
        st.stop()

    # ── Main Upload Button ──
    col_btn = st.columns([1, 2, 1])
    with col_btn[1]:
        if st.button("+ Upload", type="primary", use_container_width=True, key="main_upload_btn"):
            st.session_state["upload_mode"] = "choose"
            st.rerun()

    # ── Empty state when no popup ──
    if not st.session_state["upload_mode"]:
        st.markdown("""
        <div class="empty-state">
          <div class="empty-icon">&#128194;</div>
          <div class="empty-title">Click Upload to add content</div>
          <div class="empty-sub">Upload a file or paste a URL to scrape &mdash; output is always a .md file</div>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    # ── Popup: choose mode ──
    st.markdown("""
    <div class="card card-accent">
      <div style="font-weight:700;font-size:1rem;color:var(--text);margin-bottom:2px;">Add Content</div>
      <div style="font-size:0.8rem;color:var(--text-3);">Choose how you want to add content</div>
    </div>
    """, unsafe_allow_html=True)

    opt_col1, opt_col2 = st.columns(2)
    with opt_col1:
        if st.button("File Upload", use_container_width=True, type="primary" if st.session_state["upload_mode"] == "file" else "secondary", key="opt_file"):
            st.session_state["upload_mode"] = "file"
            st.rerun()
    with opt_col2:
        if st.button("URL", use_container_width=True, type="primary" if st.session_state["upload_mode"] == "url" else "secondary", key="opt_url"):
            st.session_state["upload_mode"] = "url"
            st.rerun()

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ── File Upload mode ──
    if st.session_state["upload_mode"] == "file":
        uploaded = st.file_uploader(
            "Drop your file here",
            type=["pdf", "docx", "doc", "txt", "md", "png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif"],
            label_visibility="collapsed",
        )

        if uploaded:
            st.markdown(f"""
            <div class="card" style="margin:0.5rem 0;">
              <div class="file-row">
                <div class="file-icon-box file-icon-upload">&#128206;</div>
                <div class="file-info">
                  <div class="file-name">{uploaded.name}</div>
                  <div class="file-detail">{fmt_bytes(uploaded.size)}</div>
                </div>
                <span class="badge badge-upload">Ready</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("Upload & Convert to .md", type="primary", key="upload_file_btn"):
                with st.spinner("Processing... Converting to markdown"):
                    data, err = api("POST", "/upload", files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
                if err:
                    st.error(err)
                else:
                    st.session_state["upload_result"] = data
                    st.session_state["upload_mode"] = None
                    st.rerun()

    # ── URL mode ──
    elif st.session_state["upload_mode"] == "url":
        st.markdown("""
        <div class="info-pill">Paste a URL and click <strong>Fetch Info</strong> to scrape the page and convert to markdown</div>
        """, unsafe_allow_html=True)

        url_col, btn_col = st.columns([4, 1])
        with url_col:
            url = st.text_input("URL", placeholder="https://example.com/page", label_visibility="collapsed", key="scrape_url_input")
        with btn_col:
            fetch_clicked = st.button("Fetch Info", type="primary", use_container_width=True, key="fetch_info_btn")

        if fetch_clicked and url.strip():
            with st.spinner("Fetching & converting to markdown..."):
                data, err = api("POST", "/scrape", json={"url": url.strip()})
            if err:
                st.error(err)
            else:
                st.session_state["upload_result"] = data
                st.session_state["upload_mode"] = None
                st.rerun()
        elif fetch_clicked and not url.strip():
            st.warning("Please enter a URL first.")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Cancel", type="secondary", use_container_width=True):
        st.session_state["upload_mode"] = None
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# INDEX TOOLS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Index Tools":
    col_h, col_r = st.columns([5, 1])
    with col_h:
        st.markdown("""
        <div class="page-hero">
          <div class="page-hero-icon">&#9881;</div>
          <div class="page-hero-text">
            <h1>Index Tools</h1>
            <div class="page-hero-sub">Manage the FAISS vector index and API health</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with col_r:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Refresh", use_container_width=True):
            st.rerun()

    stats, err = api("GET", "/rag/index/stats")
    if err:
        st.error(err)
    else:
        c1, c2 = st.columns(2)
        c1.metric("Indexed Documents", stats.get("total_documents", 0))
        c2.metric("Total Vectors", stats.get("total_vectors", 0))
        ids = stats.get("indexed_file_ids", [])
        if ids:
            with st.expander(f"Indexed File IDs  ({len(ids)})"):
                for fid in ids:
                    st.code(fid, language=None)

    st.markdown("---")

    # Rebuild
    st.markdown("""
    <div class="tool-card">
      <div class="tool-card-title">Rebuild Full Index</div>
      <div class="tool-card-desc">Re-embeds all stored documents from scratch. This may take several minutes and will use OpenAI API credits.</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Rebuild Index", type="primary"):
        with st.spinner("Rebuilding index from scratch..."):
            data, err = api("POST", "/rag/index/rebuild")
        if err:
            st.error(err)
        else:
            st.success(data.get("message", "Done!"))
            st.metric("Total Vectors After Rebuild", data.get("total_vectors", ""))

    st.markdown("---")

    # Remove document
    st.markdown("""
    <div class="tool-card">
      <div class="tool-card-title">Remove Document from Index</div>
      <div class="tool-card-desc">Removes all vectors for a specific file without deleting the document itself.</div>
    </div>
    """, unsafe_allow_html=True)
    rid = st.text_input("File ID", placeholder="Paste a file_id here...", key="rid_input")
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
      <div class="tool-card-title">API Health Check</div>
      <div class="tool-card-desc">Verify that the FastAPI backend is reachable and responding.</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Ping API"):
        data, err = api("GET", "/")
        if err:
            st.error(err)
        else:
            st.success(f"API is running: {data.get('message', 'OK')}")


# ═══════════════════════════════════════════════════════════════════════════════
# FLOATING CHAT WIDGET (appears on every page)
# ═══════════════════════════════════════════════════════════════════════════════
if "chat_msgs" not in st.session_state:
    st.session_state["chat_msgs"] = []
if "chat_topk" not in st.session_state:
    st.session_state["chat_topk"] = 5
if "chat_open" not in st.session_state:
    st.session_state["chat_open"] = False

# Toggle button in sidebar
st.sidebar.markdown("---")
if st.sidebar.button("💬 Chat Assistant", use_container_width=True):
    st.session_state["chat_open"] = not st.session_state["chat_open"]
    st.rerun()

if st.session_state["chat_open"]:
    # Build messages HTML
    msgs = st.session_state["chat_msgs"]
    if not msgs:
        body_html = """
        <div class="cw-empty">
          <div class="cw-empty-icon">&#128172;</div>
          <div class="cw-empty-title">Ask me anything</div>
          <div class="cw-empty-sub">About your indexed documents</div>
        </div>"""
    else:
        body_html = ""
        for m in msgs:
            ts = m.get("ts", "")
            body_html += f'<div class="cw-ts">{ts}</div>'
            if m["role"] == "user":
                body_html += f"""
                <div class="cw-msg-user">
                  <div class="cw-msg-user-bubble">{m["content"]}</div>
                </div>"""
            else:
                content_html = md_to_html(m["content"])
                body_html += f"""
                <div class="cw-msg-bot">
                  <div class="cw-msg-bot-av">C</div>
                  <div class="cw-msg-bot-bubble">{content_html}</div>
                </div>"""

    # Render the floating widget as HTML + Streamlit input
    st.markdown(f"""
    <div class="chat-widget" id="chatWidget">
      <div class="cw-header">
        <div class="cw-avatar">C</div>
        <div>
          <div class="cw-header-name">Document Assistant</div>
          <div class="cw-header-status">Online</div>
        </div>
      </div>
      <div class="cw-messages" id="cwMessages">{body_html}</div>
    </div>
    <script>
      var el = document.getElementById('cwMessages');
      if (el) el.scrollTop = el.scrollHeight;
    </script>
    """, unsafe_allow_html=True)

    # Chat input row (rendered at the bottom of the page, but functional)
    chat_c1, chat_c2, chat_c3 = st.columns([4, 1, 1])
    with chat_c1:
        query = st.text_input("msg", placeholder="Type a message...", label_visibility="collapsed", key="chat_inp")
    with chat_c2:
        send = st.button("Send", type="primary", use_container_width=True, key="chat_send")
    with chat_c3:
        if st.button("Clear", use_container_width=True, key="chat_clear"):
            st.session_state["chat_msgs"] = []
            st.rerun()

    if send and query.strip():
        st.session_state["chat_msgs"].append({"role": "user", "content": query.strip(), "ts": now_str()})
        with st.spinner("Thinking..."):
            data, err = api("POST", "/rag/query", json={"query": query.strip(), "top_k": st.session_state["chat_topk"]})
        answer = f"Error: {err}" if err else data.get("answer", "No answer returned.")
        st.session_state["chat_msgs"].append({"role": "assistant", "content": answer, "ts": now_str()})
        st.rerun()

else:
    # Show floating chat button when closed
    st.markdown("""
    <style>
      .chat-fab-hint {
        position: fixed; bottom: 28px; right: 28px; z-index: 9999;
        pointer-events: none;
      }
      .chat-fab-hint .fab-dot {
        width: 56px; height: 56px; border-radius: 50%;
        background: #3a3a50; border: 2px solid #4a4a62;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.4rem; color: #e8e8ef;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        animation: fab-pulse 2s infinite;
      }
      @keyframes fab-pulse {
        0%, 100% { box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
        50% { box-shadow: 0 4px 28px rgba(78,202,122,0.3); }
      }
    </style>
    <div class="chat-fab-hint">
      <div class="fab-dot">&#128172;</div>
    </div>
    """, unsafe_allow_html=True)
