import streamlit as st
import requests
import time

# ─── Configuration ───────────────────────────────────────────────────────────

st.set_page_config(
    page_title="CDP Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown li,
    section[data-testid="stSidebar"] label {
        color: #cbd5e1 !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #ffffff !important;
    }

    /* Card-like containers */
    div[data-testid="stExpander"] {
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }

    /* Metric cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
    }
    div[data-testid="stMetric"] label {
        color: #64748b !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #3b82f6 !important;
    }

    /* Chat messages */
    .stChatMessage {
        border-radius: 12px;
    }

    /* Buttons */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.15s;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 20px;
    }

    /* File badges */
    .file-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
    .badge-uploaded { background: #dbeafe; color: #1d4ed8; }
    .badge-scraped { background: #dcfce7; color: #16a34a; }

    /* Hide default streamlit elements for cleaner look */
    #MainMenu { visibility: hidden; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🤖 CDP Assistant")
    st.caption("Admin Dashboard")
    st.markdown("---")

    API_URL = st.text_input("🔗 API URL", value="http://localhost:8000")

    st.markdown("---")

    page = st.radio(
        "📍 Navigation",
        ["💬 RAG Chat", "📄 Content Management", "⚙️ Settings"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.caption("CDP Chatbot Admin v2.0")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def api_get(path):
    try:
        r = requests.get(f"{API_URL}{path}", timeout=30)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def api_post(path, json_body=None, files=None, timeout=60):
    try:
        r = requests.post(f"{API_URL}{path}", json=json_body, files=files, timeout=timeout)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def api_delete(path):
    try:
        r = requests.delete(f"{API_URL}{path}", timeout=30)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def format_bytes(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


# ═══════════════════════════════════════════════════════════════════════════════
#  RAG CHAT PAGE
# ═══════════════════════════════════════════════════════════════════════════════

if page == "💬 RAG Chat":
    st.title("💬 RAG Chat")
    st.markdown("Ask questions about your documents — powered by FAISS + OpenAI.")

    # Top-K setting
    col1, col2 = st.columns([4, 1])
    with col2:
        top_k = st.number_input("Top K chunks", min_value=1, max_value=20, value=5)

    st.markdown("---")

    # Chat messages
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

    # Chat input
    query = st.chat_input("Ask a question about your documents...")
    if query:
        st.session_state.chat_messages.append({"role": "user", "content": query})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(query)

        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("🔎 Searching knowledge base..."):
                resp, err = api_post(
                    "/rag/query",
                    json_body={"query": query, "top_k": top_k},
                )
            if err:
                st.error(f"❌ {err}")
            else:
                answer = resp.get("answer", "No response.")
                st.markdown(answer)
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": answer,
                })

    # Clear chat button
    if st.session_state.chat_messages:
        if st.button("🗑️ Clear Chat"):
            st.session_state.chat_messages = []
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  CONTENT MANAGEMENT PAGE
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "📄 Content Management":
    st.title("📄 Content Management")
    st.markdown("Upload files, scrape URLs, and manage your knowledge base content.")

    tab_files, tab_upload, tab_scrape = st.tabs(["📂 Files", "⬆️ Upload", "🌐 Scrape URL"])

    # ─── Files Tab ───────────────────────────────────────────────────────
    with tab_files:
        col_refresh, col_spacer = st.columns([1, 5])
        with col_refresh:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()

        files_resp, err = api_get("/files")
        if err:
            st.error(f"❌ {err}")
        elif files_resp:
            files = files_resp.get("files", [])
            if not files:
                st.info("📭 No files yet. Upload or scrape to add content.")
            else:
                st.markdown(f"**{len(files)} files** in your knowledge base")

                for f in files:
                    with st.expander(f"📄 {f['filename']}"):
                        # Info row
                        c1, c2, c3, c4 = st.columns(4)
                        c1.markdown(f"**Type:** `{f['type']}`")
                        c2.markdown(f"**Size:** {format_bytes(f['size_bytes'])}")
                        c3.markdown(f"**Pages:** {f.get('page_count') or 'N/A'}")
                        c4.markdown(f"**JSON:** {'✅' if f.get('has_json') else '—'}")

                        st.caption(f"File ID: `{f['file_id']}`")

                        if f.get("url"):
                            st.caption(f"Source: {f['url']}")

                        # Actions
                        btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 3])
                        with btn_col1:
                            if st.button("👁️ View", key=f"view_{f['file_id']}", use_container_width=True):
                                content_resp, cerr = api_get(f"/content/{f['file_id']}")
                                if cerr:
                                    st.error(cerr)
                                else:
                                    st.session_state[f"viewing_{f['file_id']}"] = True
                                    st.session_state[f"content_{f['file_id']}"] = content_resp.get("content", "")

                        with btn_col2:
                            if st.button("🗑️ Delete", key=f"del_{f['file_id']}", type="secondary", use_container_width=True):
                                resp, derr = api_delete(f"/content/{f['file_id']}")
                                if derr:
                                    st.error(derr)
                                else:
                                    st.success("✅ Deleted successfully")
                                    time.sleep(0.5)
                                    st.rerun()

                        # View content area (read-only)
                        if st.session_state.get(f"viewing_{f['file_id']}"):
                            content_val = st.session_state.get(f"content_{f['file_id']}", "")
                            st.text_area(
                                "Content (read-only)",
                                value=content_val,
                                height=300,
                                key=f"view_content_{f['file_id']}",
                                disabled=True,
                            )

    # ─── Upload Tab ──────────────────────────────────────────────────────
    with tab_upload:
        st.markdown("#### Upload a document to your knowledge base")

        uploaded = st.file_uploader(
            "Choose a file",
            type=["pdf", "txt", "md", "png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif"],
            help="Supported: PDF, TXT, MD, PNG, JPG, JPEG, WEBP, BMP, TIFF",
        )

        if uploaded:
            st.markdown(f"**Selected:** `{uploaded.name}` ({format_bytes(uploaded.size)})")

            if st.button("⬆️ Upload File", type="primary"):
                with st.spinner("⏳ Uploading and processing (OCR may take a moment)..."):
                    resp, err = api_post(
                        "/upload",
                        files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")},
                        timeout=300,
                    )
                if err:
                    st.error(f"❌ {err}")
                else:
                    st.success(f"✅ Uploaded: **{resp.get('filename')}**")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("File ID", resp["file_id"][:12] + "...")
                    col2.metric("Size", format_bytes(resp.get("sizeBytes", 0)))
                    col3.metric("Pages", resp.get("page_count", "N/A"))

    # ─── Scrape Tab ──────────────────────────────────────────────────────
    with tab_scrape:
        st.markdown("#### Scrape a web page into your knowledge base")

        url = st.text_input("URL to scrape", placeholder="https://example.com/page")

        if url and st.button("🌐 Scrape URL", type="primary"):
            with st.spinner("⏳ Scraping and processing..."):
                resp, err = api_post("/scrape", json_body={"url": url})
            if err:
                st.error(f"❌ {err}")
            else:
                st.success(f"✅ Scraped successfully!")
                st.markdown(f"**File ID:** `{resp['file_id']}`")
                with st.expander("Preview scraped content"):
                    st.text(resp.get("content", "")[:2000])


# ═══════════════════════════════════════════════════════════════════════════════
#  SETTINGS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "⚙️ Settings":
    st.title("⚙️ Settings")

    # ─── API Status ──────────────────────────────────────────────────────
    st.subheader("🔗 API Status")
    health, err = api_get("/")
    if err:
        st.error("🔴 API is **Offline**")
        st.caption(f"Error: {err}")
    else:
        st.success(f"🟢 API is **Online** — {health.get('message', 'OK')}")

    st.markdown("---")

    # ─── Index Statistics ────────────────────────────────────────────────
    st.subheader("📊 Index Statistics")

    stats, err = api_get("/rag/index/stats")
    if stats:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Vectors", stats["total_vectors"])
        c2.metric("Total Documents", stats["total_documents"])
        c3.metric("Indexed File IDs", len(stats.get("indexed_file_ids", [])))

        if stats.get("indexed_file_ids"):
            with st.expander("View indexed file IDs"):
                for fid in stats["indexed_file_ids"]:
                    st.code(fid, language=None)
    elif err:
        st.warning(f"Could not load stats: {err}")

    st.markdown("---")

    # ─── Index Controls ──────────────────────────────────────────────────
    st.subheader("🛠️ Index Controls")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Rebuild FAISS Index**")
        st.caption("Re-indexes all stored documents from scratch.")
        if st.button("🔨 Rebuild Index", use_container_width=True):
            with st.spinner("Rebuilding index..."):
                resp, err = api_post("/rag/index/rebuild")
            if err:
                st.error(err)
            else:
                st.success(resp.get("message", "Done"))
                st.metric("Total Vectors", resp.get("total_vectors", 0))

    with col2:
        st.markdown("**Remove Document from Index**")
        st.caption("Remove a specific document's chunks from the FAISS index.")
        remove_fid = st.text_input("File ID to remove")
        if remove_fid and st.button("🗑️ Remove from Index", use_container_width=True):
            resp, err = api_delete(f"/rag/index/{remove_fid}")
            if err:
                st.error(err)
            else:
                st.success(resp.get("message", "Removed"))
