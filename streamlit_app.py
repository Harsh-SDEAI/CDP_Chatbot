import streamlit as st
import requests
import uuid

# ─── Configuration ───────────────────────────────────────────────────────────

st.set_page_config(page_title="CDP Admin", layout="wide")

if "theme" not in st.session_state:
    st.session_state.theme = "light"

API_URL = st.sidebar.text_input("API URL", value="http://localhost:8000")

st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["Chat", "Content Management", "History", "Settings"],
)

st.sidebar.markdown("---")
st.sidebar.caption("CDP Chatbot Admin")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def api_get(path):
    try:
        r = requests.get(f"{API_URL}{path}", timeout=30)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def api_post(path, json_body=None, files=None):
    try:
        r = requests.post(f"{API_URL}{path}", json=json_body, files=files, timeout=60)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def api_put(path, json_body):
    try:
        r = requests.put(f"{API_URL}{path}", json=json_body, timeout=30)
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


# ─── Chat (unified: Chatbot + RAG) ──────────────────────────────────────────

if page == "Chat":
    st.title("CDP Chat")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        userid = st.number_input("User ID", min_value=1, value=1, step=1)
    with col2:
        if "session_id" not in st.session_state:
            st.session_state.session_id = str(uuid.uuid4())
        session_id = st.text_input("Session ID", value=st.session_state.session_id)
    with col3:
        st.write("")
        st.write("")
        if st.button("New Session"):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.chat_messages = []
            st.rerun()

    st.markdown("---")

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

    query = st.chat_input("Ask a question...")
    if query:
        st.session_state.chat_messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                resp, err = api_post(
                    "/chat",
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


# ─── Content Management ─────────────────────────────────────────────────────

elif page == "Content Management":
    st.title("Content Management")

    tab_list, tab_upload, tab_scrape = st.tabs(["Files", "Upload", "Scrape URL"])

    with tab_list:
        if st.button("Refresh"):
            st.rerun()

        files_resp, err = api_get("/files")
        if err:
            st.error(err)
        elif files_resp:
            files = files_resp.get("files", [])
            if not files:
                st.info("No files yet. Upload or scrape to add content.")
            else:
                for f in files:
                    with st.expander(f"{f['filename']} ({f['type']})"):
                        c1, c2, c3 = st.columns(3)
                        c1.write(f"**File ID:** `{f['file_id']}`")
                        c2.write(f"**Size:** {f['size_bytes']} bytes")
                        c3.write(f"**Pages:** {f.get('page_count', 'N/A')}")

                        if st.button("View Content", key=f"view_{f['file_id']}"):
                            content_resp, cerr = api_get(f"/content/{f['file_id']}")
                            if cerr:
                                st.error(cerr)
                            else:
                                st.text_area("Content", value=content_resp.get("content", ""), height=300, key=f"content_{f['file_id']}")

                        if st.button("Delete", key=f"del_{f['file_id']}", type="secondary"):
                            resp, derr = api_delete(f"/content/{f['file_id']}")
                            if derr:
                                st.error(derr)
                            else:
                                st.success("Deleted")
                                st.rerun()

    with tab_upload:
        uploaded = st.file_uploader("Choose a file", type=["pdf", "txt", "md", "png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif"])
        if uploaded and st.button("Upload"):
            with st.spinner("Uploading..."):
                resp, err = api_post(
                    "/upload",
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")},
                )
            if err:
                st.error(err)
            else:
                st.success(f"Uploaded: {resp.get('filename')} (ID: `{resp['file_id']}`)")

    with tab_scrape:
        url = st.text_input("URL to scrape")
        if url and st.button("Scrape"):
            with st.spinner("Scraping..."):
                resp, err = api_post("/scrape", json_body={"url": url})
            if err:
                st.error(err)
            else:
                st.success(f"Scraped: {resp['file_id']}")


# ─── History ─────────────────────────────────────────────────────────────────

elif page == "History":
    st.title("Chat History")

    hist, err = api_get("/history")
    if err:
        st.error(f"Failed to load: {err}")
    else:
        entries = hist.get("conversation_history", [])
        if not entries:
            st.info("No chat history found.")
        else:
            st.write(f"**Total:** {len(entries)}")

            filter_user = st.text_input("Filter by User ID")
            filtered = entries
            if filter_user:
                filtered = [e for e in filtered if str(filter_user) == str(e.get("user_registration_id", ""))]

            for entry in filtered[:100]:
                with st.expander(f"[{entry.get('timestamp', '')}] User {entry.get('user_registration_id')} - {(entry.get('question', '') or '')[:80]}"):
                    st.markdown(f"**Q:** {entry.get('question')}")
                    st.markdown("**A:**")
                    st.html(entry.get("answer", ""))


# ─── Settings ────────────────────────────────────────────────────────────────

elif page == "Settings":
    st.title("Settings")

    st.subheader("API Status")
    health, err = api_get("/")
    if err:
        st.error("API: Offline")
    else:
        st.success(f"API: {health.get('message', 'OK')}")

    st.markdown("---")

    st.subheader("Index Controls")

    stats, err = api_get("/rag/index/stats")
    if stats:
        c1, c2 = st.columns(2)
        c1.metric("Admin Vectors", stats["total_vectors"])
        c2.metric("Admin Documents", stats["total_documents"])

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Rebuild Admin Index"):
            with st.spinner("Rebuilding..."):
                resp, err = api_post("/rag/index/rebuild")
            if err:
                st.error(err)
            else:
                st.success(resp.get("message", "Done"))

    with col2:
        if st.button("Rebuild Chatbot Index"):
            with st.spinner("Rebuilding..."):
                resp, err = api_post("/update-index")
            if err:
                st.error(err)
            else:
                st.success(f"Indexed {resp.get('documents_indexed', '?')} docs")

    with col3:
        if st.button("Update All (KB + Index)", type="primary"):
            with st.spinner("Updating..."):
                resp, err = api_post("/update-all")
            if err:
                st.error(err)
            else:
                st.success(resp.get("message", "Done"))
