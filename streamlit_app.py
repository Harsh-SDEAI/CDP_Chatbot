import streamlit as st
import requests
import json
import uuid
import time

# ─── Configuration ───────────────────────────────────────────────────────────

st.set_page_config(page_title="CDP Chatbot Admin", layout="wide", page_icon="🏟️")

ADMIN_API = st.sidebar.text_input("Admin API URL", value="http://localhost:8000")
CHATBOT_API = st.sidebar.text_input("Chatbot API URL", value="http://localhost:8001")

st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Content Management",
        "Document Viewer",
        "RAG Query",
        "Chatbot",
        "Chat History",
        "Settings",
    ],
)

st.sidebar.markdown("---")
st.sidebar.caption("CDP Chatbot Admin Dashboard")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def api_get(base_url, path):
    try:
        r = requests.get(f"{base_url}{path}", timeout=30)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def api_post(base_url, path, json_body=None, files=None):
    try:
        r = requests.post(f"{base_url}{path}", json=json_body, files=files, timeout=60)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def api_put(base_url, path, json_body):
    try:
        r = requests.put(f"{base_url}{path}", json=json_body, timeout=30)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def api_delete(base_url, path):
    try:
        r = requests.delete(f"{base_url}{path}", timeout=30)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


# ─── Dashboard ───────────────────────────────────────────────────────────────

if page == "Dashboard":
    st.title("Dashboard")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Admin API")
        health, err = api_get(ADMIN_API, "/")
        if err:
            st.error(f"Admin API unreachable: {err}")
        else:
            st.success(health.get("message", "Connected"))

        stats, err = api_get(ADMIN_API, "/rag/index/stats")
        if stats:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Vectors", stats["total_vectors"])
            c2.metric("Total Documents", stats["total_documents"])
            c3.metric("Indexed Files", len(stats.get("indexed_file_ids", [])))

        files_resp, err = api_get(ADMIN_API, "/files")
        if files_resp:
            files = files_resp.get("files", [])
            st.metric("Stored Files", len(files))
            if files:
                st.markdown("**Recent Files:**")
                for f in files[:5]:
                    st.text(f"  {f['filename']} ({f['type']}, {f['size_bytes']} bytes)")

    with col2:
        st.subheader("Chatbot API")
        hist, err = api_get(CHATBOT_API, "/history")
        if err:
            st.error(f"Chatbot API unreachable: {err}")
        else:
            st.success("Connected")
            entries = hist.get("conversation_history", [])
            st.metric("Chat History Entries", len(entries))


# ─── Content Management ─────────────────────────────────────────────────────

elif page == "Content Management":
    st.title("Content Management")

    tab_list, tab_upload, tab_scrape = st.tabs(["File List", "Upload File", "Scrape URL"])

    # --- File List ---
    with tab_list:
        if st.button("Refresh File List"):
            st.rerun()

        files_resp, err = api_get(ADMIN_API, "/files")
        if err:
            st.error(err)
        elif files_resp:
            files = files_resp.get("files", [])
            if not files:
                st.info("No files stored yet. Upload or scrape to add content.")
            else:
                for f in files:
                    with st.expander(f"📄 {f['filename']} ({f['type']})"):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.write(f"**File ID:** `{f['file_id']}`")
                        c2.write(f"**Size:** {f['size_bytes']} bytes")
                        c3.write(f"**Has JSON:** {'Yes' if f.get('has_json') else 'No'}")
                        c4.write(f"**Pages:** {f.get('page_count', 'N/A')}")

                        if f.get("url"):
                            st.write(f"**Source URL:** {f['url']}")

                        col_view, col_del = st.columns(2)
                        with col_view:
                            if st.button("View", key=f"view_{f['file_id']}"):
                                st.session_state["viewer_file_id"] = f["file_id"]
                                st.info("Go to 'Document Viewer' page to see this file.")
                        with col_del:
                            if st.button("Delete", key=f"del_{f['file_id']}", type="secondary"):
                                resp, err = api_delete(ADMIN_API, f"/content/{f['file_id']}")
                                if err:
                                    st.error(err)
                                else:
                                    st.success(resp.get("message", "Deleted"))
                                    st.rerun()

    # --- Upload ---
    with tab_upload:
        st.subheader("Upload a File")
        st.caption("Supported: PDF, TXT, MD, PNG, JPG, JPEG, WEBP, BMP, TIFF")
        uploaded = st.file_uploader("Choose a file", type=["pdf", "txt", "md", "png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif"])
        if uploaded and st.button("Upload"):
            with st.spinner("Uploading and processing..."):
                resp, err = api_post(
                    ADMIN_API, "/upload",
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")},
                )
            if err:
                st.error(err)
            else:
                st.success(f"Uploaded! File ID: `{resp['file_id']}`")
                st.write(f"**Filename:** {resp.get('filename')}")
                st.write(f"**Size:** {resp.get('sizeBytes')} bytes")
                if resp.get("page_count"):
                    st.write(f"**Pages:** {resp['page_count']}, **Blocks:** {resp.get('block_count')}")
                with st.expander("Preview extracted content"):
                    st.text(resp.get("content", "")[:3000])

    # --- Scrape ---
    with tab_scrape:
        st.subheader("Scrape a URL")
        url = st.text_input("Enter URL to scrape")
        if url and st.button("Scrape"):
            with st.spinner("Scraping..."):
                resp, err = api_post(ADMIN_API, "/scrape", json_body={"url": url})
            if err:
                st.error(err)
            else:
                st.success(f"Scraped! File ID: `{resp['file_id']}`")
                with st.expander("Preview scraped content"):
                    st.text(resp.get("content", "")[:3000])


# ─── Document Viewer ─────────────────────────────────────────────────────────

elif page == "Document Viewer":
    st.title("Document Viewer")

    file_id = st.text_input("File ID", value=st.session_state.get("viewer_file_id", ""))

    if file_id:
        tab_md, tab_json = st.tabs(["Markdown Content", "Structured JSON"])

        # --- Markdown ---
        with tab_md:
            content_resp, err = api_get(ADMIN_API, f"/content/{file_id}")
            if err:
                st.error(err)
            else:
                st.write(f"**Filename:** {content_resp.get('filename')} | **Type:** {content_resp.get('type')}")
                if content_resp.get("url"):
                    st.write(f"**Source URL:** {content_resp['url']}")

                edited = st.text_area("Edit content", value=content_resp.get("content", ""), height=400)

                if st.button("Save Changes"):
                    resp, err = api_put(ADMIN_API, "/content", json_body={"file_id": file_id, "content": edited})
                    if err:
                        st.error(err)
                    else:
                        st.success(resp.get("message", "Saved"))

                with st.expander("Rendered Preview"):
                    st.markdown(content_resp.get("content", ""))

        # --- Structured JSON ---
        with tab_json:
            json_resp, err = api_get(ADMIN_API, f"/content/{file_id}/json")
            if err:
                st.warning("No structured JSON available for this file.")
            else:
                st.write(f"**Pages:** {json_resp.get('page_count')} | **Extracted:** {json_resp.get('extracted_at')}")
                blocks = json_resp.get("blocks", [])
                st.write(f"**Blocks:** {len(blocks)}")
                for i, block in enumerate(blocks):
                    with st.expander(f"Block {i+1}: {block['type']} (pages {block.get('pages', [])})"):
                        st.json(block)
    else:
        st.info("Enter a file ID above, or click 'View' on a file in Content Management.")


# ─── RAG Query ───────────────────────────────────────────────────────────────

elif page == "RAG Query":
    st.title("RAG Query (Admin API)")
    st.caption("Test the Admin Content Manager's RAG system (GPT-4o + FAISS)")

    if "rag_messages" not in st.session_state:
        st.session_state.rag_messages = []

    top_k = st.slider("Top K chunks", min_value=1, max_value=20, value=5)

    # Display chat history
    for msg in st.session_state.rag_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    query = st.chat_input("Ask a question...")
    if query:
        st.session_state.rag_messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        with st.chat_message("assistant"):
            with st.spinner("Searching..."):
                resp, err = api_post(ADMIN_API, "/rag/query", json_body={"query": query, "top_k": top_k})
            if err:
                st.error(err)
            else:
                answer = resp.get("answer", "No answer returned.")
                st.markdown(answer)
                st.session_state.rag_messages.append({"role": "assistant", "content": answer})

    if st.button("Clear Chat"):
        st.session_state.rag_messages = []
        st.rerun()


# ─── Chatbot ─────────────────────────────────────────────────────────────────

elif page == "Chatbot":
    st.title("Chatbot (Production API)")
    st.caption("Test the Cooperstown Dreams Park chatbot (GPT-3.5 + LlamaIndex)")

    col1, col2 = st.columns(2)
    with col1:
        userid = st.number_input("User ID", min_value=1, value=1, step=1)
    with col2:
        if "session_id" not in st.session_state:
            st.session_state.session_id = str(uuid.uuid4())
        session_id = st.text_input("Session ID", value=st.session_state.session_id)
        if st.button("New Session"):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.chat_messages = []
            st.rerun()

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                st.html(msg["content"])
                if msg.get("time_taken"):
                    st.caption(f"Response time: {msg['time_taken']:.2f}s")
            else:
                st.markdown(msg["content"])

    query = st.chat_input("Ask the chatbot...")
    if query:
        st.session_state.chat_messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                resp, err = api_post(
                    CHATBOT_API, "/chat",
                    json_body={"query": query, "userid": int(userid), "sessionid": session_id},
                )
            if err:
                st.error(err)
            else:
                answer = resp.get("response", "No response.")
                time_taken = resp.get("time_taken", 0)
                st.html(answer)
                st.caption(f"Response time: {time_taken:.2f}s")
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": answer,
                    "time_taken": time_taken,
                })


# ─── Chat History ────────────────────────────────────────────────────────────

elif page == "Chat History":
    st.title("Chat History")

    if st.button("Refresh"):
        st.rerun()

    hist, err = api_get(CHATBOT_API, "/history")
    if err:
        st.error(f"Failed to load history: {err}")
    else:
        entries = hist.get("conversation_history", [])
        if not entries:
            st.info("No chat history found.")
        else:
            st.write(f"**Total entries:** {len(entries)}")

            # Filters
            col1, col2 = st.columns(2)
            with col1:
                filter_session = st.text_input("Filter by Session ID")
            with col2:
                filter_user = st.text_input("Filter by User ID")

            filtered = entries
            if filter_session:
                filtered = [e for e in filtered if filter_session.lower() in str(e.get("session_id", "")).lower()]
            if filter_user:
                filtered = [e for e in filtered if str(filter_user) == str(e.get("user_registration_id", ""))]

            st.write(f"**Showing:** {len(filtered)} entries")

            for i, entry in enumerate(filtered[:100]):
                with st.expander(
                    f"[{entry.get('timestamp', 'N/A')}] User {entry.get('user_registration_id')} — {(entry.get('question', '') or '')[:80]}..."
                ):
                    st.markdown(f"**Session:** `{entry.get('session_id')}`")
                    st.markdown(f"**Question:** {entry.get('question')}")
                    st.markdown("**Answer:**")
                    st.html(entry.get("answer", ""))


# ─── Settings ────────────────────────────────────────────────────────────────

elif page == "Settings":
    st.title("Settings & Admin Controls")

    # --- Health Checks ---
    st.subheader("API Health Checks")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Admin API**")
        health, err = api_get(ADMIN_API, "/")
        if err:
            st.error(f"Unreachable: {err}")
        else:
            st.success(health.get("message", "OK"))
    with col2:
        st.markdown("**Chatbot API**")
        hist, err = api_get(CHATBOT_API, "/history")
        if err:
            st.error(f"Unreachable: {err}")
        else:
            st.success("Connected")

    st.markdown("---")

    # --- Admin Index Controls ---
    st.subheader("Admin API — Index Controls")

    stats, err = api_get(ADMIN_API, "/rag/index/stats")
    if err:
        st.warning(f"Could not fetch index stats: {err}")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Vectors", stats["total_vectors"])
        c2.metric("Documents", stats["total_documents"])
        c3.metric("Indexed Files", len(stats.get("indexed_file_ids", [])))

        if stats.get("indexed_file_ids"):
            with st.expander("Indexed File IDs"):
                for fid in stats["indexed_file_ids"]:
                    st.code(fid)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Rebuild Admin Index", type="primary"):
            with st.spinner("Rebuilding index..."):
                resp, err = api_post(ADMIN_API, "/rag/index/rebuild")
            if err:
                st.error(err)
            else:
                st.success(resp.get("message", "Done"))

    with col2:
        remove_id = st.text_input("File ID to remove from index")
        if remove_id and st.button("Remove from Index"):
            resp, err = api_delete(ADMIN_API, f"/rag/index/{remove_id}")
            if err:
                st.error(err)
            else:
                st.success(resp.get("message", "Removed"))

    st.markdown("---")

    # --- Chatbot KB Controls ---
    st.subheader("Chatbot API — Knowledge Base Controls")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Export KB"):
            with st.spinner("Exporting Q&A pairs..."):
                resp, err = api_post(CHATBOT_API, "/update-kb")
            if err:
                st.error(err)
            else:
                st.success(f"Status: {resp.get('status')}")
                if resp.get("files"):
                    st.write(f"Files created: {resp['files']}")
                if resp.get("message"):
                    st.info(resp["message"])

    with col2:
        if st.button("Rebuild Chatbot Index"):
            with st.spinner("Rebuilding FAISS index..."):
                resp, err = api_post(CHATBOT_API, "/update-index")
            if err:
                st.error(err)
            else:
                st.success(f"Indexed {resp.get('documents_indexed', '?')} documents")

    with col3:
        if st.button("Update All (KB + Index)", type="primary"):
            with st.spinner("Running full update..."):
                resp, err = api_post(CHATBOT_API, "/update-all")
            if err:
                st.error(err)
            else:
                st.success(resp.get("message", "Done"))
                with st.expander("Details"):
                    st.json(resp)
