"""
Concierge Streamlit Frontend — Monitor, Files, and RAG Chat pages.
Connects to concierge_api.py running on port 8001.

Run: streamlit run streamlit_app_2.py --server.port 8502
"""

import streamlit as st
import requests
from datetime import datetime

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Concierge Monitor & Chat",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Light Theme with Navy Sidebar CSS ─────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg:             #f5f7fa;
    --bg-2:           #ffffff;
    --sidebar-bg:     #1a2234;
    --sidebar-text:   #c8d0dc;
    --sidebar-active: #2d6cdf;
    --surface:        #ffffff;
    --border:         #e2e6ed;
    --border-2:       #d0d5dd;
    --text:           #1a1f2e;
    --text-2:         #5a6274;
    --text-3:         #8b95a5;
    --accent:         #2d6cdf;
    --green:          #12b76a;
    --green-bg:       rgba(18,183,106,0.10);
    --red:            #f04438;
    --red-bg:         rgba(240,68,56,0.08);
    --orange:         #f79009;
    --radius:         10px;
    --radius-lg:      14px;
    --shadow-sm:      0 1px 3px rgba(0,0,0,0.06);
    --shadow:         0 2px 8px rgba(0,0,0,0.08);
}

html, body, [class*="css"], .stApp, .main {
    font-family: 'Inter', -apple-system, sans-serif !important;
    background: var(--bg) !important;
    color: var(--text) !important;
}
.main .block-container {
    padding: 2rem 2.5rem 4rem !important;
    max-width: 1100px !important;
}

::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.12); border-radius: 8px; }

/* ── Dark Navy Sidebar ── */
[data-testid="stSidebar"] {
    background: var(--sidebar-bg) !important;
    border-right: none !important;
}
[data-testid="stSidebar"] * {
    color: var(--sidebar-text) !important;
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    padding: 9px 14px !important;
    border-radius: 8px !important;
    color: var(--sidebar-text) !important;
}
[data-testid="stSidebar"] .stRadio label[data-checked="true"],
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:has(input:checked) {
    background: var(--sidebar-active) !important;
    color: #ffffff !important;
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #ffffff !important;
}
[data-testid="stSidebar"] .stTextInput input {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    color: #ffffff !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: var(--sidebar-active) !important;
    color: #ffffff !important;
    border: none !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.1) !important;
}

/* ── Main Content ── */
h1 { font-size: 1.5rem !important; font-weight: 700 !important; letter-spacing: -0.03em !important; color: var(--text) !important; }
h2 { font-size: 1.1rem !important; font-weight: 600 !important; color: var(--text) !important; }
h3 { font-size: 0.95rem !important; font-weight: 600 !important; color: var(--text) !important; }

.stButton > button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.84rem !important;
    border-radius: 8px !important;
    border: 1px solid var(--border-2) !important;
    background: var(--bg-2) !important;
    color: var(--text) !important;
}
.stButton > button[kind="primary"],
.stButton > button[data-testid="stFormSubmitButton"] {
    background: var(--accent) !important;
    color: #ffffff !important;
    border: none !important;
}

/* ── Input Fields ── */
.stTextInput input, .stSelectbox select, .stTextArea textarea {
    background: var(--bg-2) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    border-radius: 8px !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(45,108,223,0.15) !important;
}

/* ── Status Badges ── */
.status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.78rem;
    font-weight: 600;
}
.status-new       { background: var(--green-bg); color: var(--green); }
.status-unchanged { background: #f0f1f3; color: var(--text-3); }
.status-updated   { background: rgba(45,108,223,0.10); color: var(--accent); }
.status-error     { background: var(--red-bg); color: var(--red); }

/* ── Monitor Card ── */
.monitor-card {
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    box-shadow: var(--shadow-sm);
}
.monitor-card strong { color: var(--text) !important; }
.monitor-card span { color: var(--text-3) !important; }

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: var(--bg-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 1rem !important;
    box-shadow: var(--shadow-sm) !important;
}
[data-testid="stMetric"] label,
[data-testid="stMetricLabel"] {
    color: var(--text-2) !important;
    font-weight: 600 !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"],
[data-testid="stMetricValue"] {
    color: var(--text) !important;
    font-weight: 700 !important;
}

/* ── Slider label ── */
.stSlider label, .stSlider p { color: var(--text-2) !important; }

/* ── Chat Messages ── */
[data-testid="stChatMessage"] {
    background: var(--bg-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ── Slider ── */
.stSlider [data-testid="stThumbValue"] { color: var(--text) !important; }

/* ── Captions & Info ── */
.stCaption, [data-testid="stCaption"] { color: var(--text-3) !important; }

/* ── Footer ── */
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── API Helper ────────────────────────────────────────────────────────────────

def _default_api_base():
    """Auto-detect API base URL so teammates on the same network don't need to change it."""
    try:
        host = st.context.headers.get("Host", "localhost:8502").split(":")[0]
    except Exception:
        host = "localhost"
    return f"http://{host}:8001"

def api(method: str, path: str, **kwargs):
    base = st.session_state.get("api_base", _default_api_base())
    url = f"{base}{path}"
    try:
        resp = getattr(requests, method)(url, timeout=60, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error(f"Cannot connect to API at {base}. Is concierge_api.py running?")
        return None
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", "")
        except Exception:
            pass
        st.error(f"API error: {e.response.status_code} — {detail or str(e)}")
        return None
    except Exception as e:
        st.error(f"Request failed: {e}")
        return None


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("# Concierge")
    st.markdown("Content Monitor & RAG Chat")
    st.markdown("---")

    page = st.radio("Navigate", ["Monitor", "Files", "RAG Chat"], label_visibility="collapsed")

    st.markdown("---")
    st.session_state["api_base"] = st.text_input(
        "API Base URL",
        value=st.session_state.get("api_base", _default_api_base()),
    )


# ── Page: Monitor ────────────────────────────────────────────────────────────

if page == "Monitor":
    st.markdown("# URL Monitor")
    st.caption("Add URLs to monitor for content changes with SHA-256 hashing")

    # Add URL form
    with st.container():
        st.markdown("## Add URL")
        col1, col2 = st.columns([3, 1])
        with col1:
            new_url = st.text_input("URL to monitor", placeholder="https://example.com/page", label_visibility="collapsed")
        with col2:
            interval_map = {"Every 6h": 6, "Every 12h": 12, "Daily": 24, "Weekly": 168}
            interval_label = st.selectbox("Interval", list(interval_map.keys()), index=2, label_visibility="collapsed")
            interval_hours = interval_map[interval_label]

        if st.button("Start Monitoring", type="primary"):
            if new_url:
                with st.spinner("Scraping and indexing..."):
                    result = api("post", "/monitor", json={"url": new_url, "interval_hours": interval_hours})
                if result:
                    st.success(f"Now monitoring! File: `{result.get('file_id')}`")
                    st.rerun()
            else:
                st.warning("Please enter a URL.")

    st.markdown("---")

    # Check All Now
    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.markdown("## Monitored URLs")
    with col_btn:
        if st.button("Check All Now"):
            with st.spinner("Checking all URLs..."):
                result = api("post", "/monitor/check-now")
            if result:
                for r in result.get("results", []):
                    status = r.get("status", "unknown")
                    if status == "updated":
                        st.success(f"{r['url']} — Content changed!")
                    elif status == "unchanged":
                        st.info(f"{r['url']} — No changes")
                    else:
                        st.error(f"{r['url']} — Error: {r.get('error', 'unknown')}")
                st.rerun()

    # List monitored URLs
    data = api("get", "/monitor")
    if data:
        urls = data.get("monitored_urls", [])
        if not urls:
            st.info("No URLs being monitored yet. Add one above!")
        else:
            for entry in urls:
                status = entry.get("status", "new")
                badge_class = f"status-{status}"

                last_checked = entry.get("last_checked", "")
                if last_checked:
                    try:
                        dt = datetime.fromisoformat(last_checked.replace("Z", "+00:00"))
                        last_checked = dt.strftime("%Y-%m-%d %H:%M UTC")
                    except Exception:
                        pass

                interval = entry.get("interval_hours", 24)
                interval_str = f"{interval}h" if interval < 24 else f"{interval // 24}d"

                st.markdown(f"""
                <div class="monitor-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <strong style="font-size:0.9rem;">{entry.get('url', 'N/A')}</strong>
                            <br><span style="color:var(--text-3);font-size:0.78rem;">
                                Every {interval_str} &middot; Last checked: {last_checked or 'never'} &middot; File: {entry.get('file_id', 'N/A')}
                            </span>
                        </div>
                        <span class="status-badge {badge_class}">{status}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Remove button
                if st.button(f"Remove", key=f"rm_{entry.get('file_id', '')}"):
                    api("delete", f"/monitor/{entry['file_id']}")
                    st.rerun()


# ── Page: Files ──────────────────────────────────────────────────────────────

elif page == "Files":
    st.markdown("# Scraped Files")
    st.caption("View and manage scraped content")

    data = api("get", "/files")
    if data:
        files = data.get("files", [])
        if not files:
            st.info("No files yet. Go to Monitor and add a URL!")
        else:
            for f in files:
                file_id = f["file_id"]
                col1, col2, col3 = st.columns([4, 1, 1])

                with col1:
                    st.markdown(f"**{f['filename']}**")
                    size_kb = f.get("size_bytes", 0) / 1024
                    hash_short = (f.get("content_hash") or "")[:12]
                    st.caption(f"{size_kb:.1f} KB · Hash: {hash_short}... · {f.get('url', '')}")

                with col2:
                    if st.button("View", key=f"view_{file_id}"):
                        st.session_state["view_file"] = file_id

                with col3:
                    if st.button("Delete", key=f"del_{file_id}"):
                        api("delete", f"/content/{file_id}")
                        if st.session_state.get("view_file") == file_id:
                            del st.session_state["view_file"]
                        st.rerun()

            # View file content
            if "view_file" in st.session_state:
                st.markdown("---")
                content_data = api("get", f"/content/{st.session_state['view_file']}")
                if content_data:
                    st.markdown(f"### {content_data.get('filename', 'File')}")
                    if content_data.get("url"):
                        st.caption(f"Source: {content_data['url']}")
                    st.text_area(
                        "Content",
                        value=content_data.get("content", ""),
                        height=400,
                        disabled=True,
                        label_visibility="collapsed",
                    )


# ── Page: RAG Chat ───────────────────────────────────────────────────────────

elif page == "RAG Chat":
    st.markdown("# RAG Chat")
    st.caption("Ask questions grounded in your scraped content")

    # Index stats
    stats = api("get", "/rag/index/stats")
    if stats:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Documents Indexed", stats.get("total_documents", 0))
        with col2:
            st.metric("Total Vectors", stats.get("total_vectors", 0))

    st.markdown("---")

    # Top-k slider
    top_k = st.slider("Number of context chunks", min_value=1, max_value=20, value=5)

    # Chat history
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    # Display chat history
    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    query = st.chat_input("Ask a question about your content...")
    if query:
        st.session_state["chat_history"].append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        with st.chat_message("assistant"):
            with st.spinner("Searching and generating answer..."):
                result = api("post", "/rag/query", json={"query": query, "top_k": top_k})

            if result:
                answer = result.get("answer", "No answer returned.")
                sources = result.get("sources", [])
                chunks_used = result.get("chunks_used", 0)

                st.markdown(answer)
                if sources:
                    st.caption(f"Sources: {', '.join(sources)} ({chunks_used} chunks used)")

                st.session_state["chat_history"].append({"role": "assistant", "content": answer})
            else:
                st.error("Failed to get a response from the RAG API.")

    # Clear chat
    if st.session_state["chat_history"]:
        if st.button("Clear Chat"):
            st.session_state["chat_history"] = []
            st.rerun()
