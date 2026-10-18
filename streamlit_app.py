import asyncio
import json
import logging
import os
from pathlib import Path
import time
import uuid

import inngest
import requests
import streamlit as st
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Configuration & Page Setup
# -----------------------------------------------------------------------------
load_dotenv()

st.set_page_config(
    page_title="Document AI Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

CHAT_HISTORY_FILE = Path("chat_history.json")
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_OPTIONS = {
    "Auto Cascade (Gemini Flash ➜ Qwen 2.5 ➜ Nemotron)": "auto",
    "Google Gemini 2.5 Flash (Tier 1 - Low Latency)": "google/gemini-2.5-flash",
    "Qwen 2.5 72B Instruct (Tier 2 - SOTA Reasoning)": "qwen/qwen-2.5-72b-instruct",
    "NVIDIA Nemotron 120B (Tier 3 - Free Tier Safeguard)": "nvidia/nemotron-3-super-120b-a12b:free",
}

# -----------------------------------------------------------------------------
# Inngest Client & API Helpers
# -----------------------------------------------------------------------------
@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    return inngest.Inngest(app_id="rag_app", is_production=False)


def _inngest_api_base() -> str:
    return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")


def fetch_runs(event_id: str) -> list[dict]:
    url = f"{_inngest_api_base()}/events/{event_id}/runs"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception:
        return []


def fetch_run_by_id(run_id: str) -> dict:
    url = f"{_inngest_api_base()}/runs/{run_id}"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json().get("data", {})
    except Exception:
        return {}


def wait_for_run_output(event_id: str, timeout_s: float = 120.0, poll_interval_s: float = 0.5) -> dict:
    start = time.time()
    last_status = None
    while time.time() - start <= timeout_s:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status

            if status in ("Completed", "Succeeded", "Success", "Finished"):
                output = run.get("output")
                if not output and run.get("run_id"):
                    full_run = fetch_run_by_id(run["run_id"])
                    output = full_run.get("output") or {}
                return output or {}

            if status in ("Failed", "Cancelled"):
                err_msg = ""
                if run.get("run_id"):
                    full_run = fetch_run_by_id(run["run_id"])
                    err_msg = full_run.get("error") or ""
                raise RuntimeError(f"Workflow {status}: {err_msg}".strip())

        time.sleep(poll_interval_s)

    raise TimeoutError(f"Timed out waiting for workflow completion (last status: {last_status})")


async def send_rag_query_event(question: str, top_k: int, model: str | None = None) -> str:
    client = get_inngest_client()
    event_data = {
        "question": question,
        "top_k": top_k,
    }
    if model and model != "auto":
        event_data["model"] = model

    result = await client.send(
        inngest.Event(
            name="rag/query_pdf_ai",
            data=event_data,
        )
    )
    return result[0]


async def send_rag_ingest_event(pdf_path: Path) -> None:
    client = get_inngest_client()
    await client.send(
        inngest.Event(
            name="rag/ingest_pdf",
            data={
                "pdf_path": str(pdf_path.resolve()),
                "source_id": pdf_path.name,
            },
        )
    )


# -----------------------------------------------------------------------------
# Service Health Check (Cached with 15s TTL to prevent blocking renders)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=15, show_spinner=False)
def check_services_health() -> dict[str, bool]:
    def _is_alive(url: str) -> bool:
        try:
            r = requests.get(url, timeout=1.5)
            return r.status_code < 500
        except Exception:
            return False

    return {
        "Qdrant DB (6333)": _is_alive("http://127.0.0.1:6333"),
        "Inngest Dev Server (8288)": _is_alive("http://127.0.0.1:8288"),
        "FastAPI Backend (8000)": _is_alive("http://127.0.0.1:8000/docs"),
    }


# -----------------------------------------------------------------------------
# Conversation Persistence & Multi-Session Management (O(1) dictionary lookup)
# -----------------------------------------------------------------------------
def load_all_sessions() -> dict[str, dict]:
    if not CHAT_HISTORY_FILE.exists():
        return {}
    try:
        with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.warning(f"Error loading chat history: {e}")
        return {}


def save_all_sessions(sessions: dict[str, dict]) -> None:
    try:
        with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.warning(f"Error saving chat history: {e}")


def init_session_state() -> None:
    if "sessions" not in st.session_state:
        st.session_state.sessions = load_all_sessions()

    if "active_session_id" not in st.session_state or not st.session_state.active_session_id:
        if st.session_state.sessions:
            # Pick most recently created session
            sorted_keys = sorted(
                st.session_state.sessions.keys(),
                key=lambda k: st.session_state.sessions[k].get("created_at", 0),
                reverse=True,
            )
            st.session_state.active_session_id = sorted_keys[0]
        else:
            new_id = create_new_session()
            st.session_state.active_session_id = new_id


def create_new_session(initial_title: str = "New Conversation") -> str:
    session_id = str(uuid.uuid4())
    new_session = {
        "id": session_id,
        "title": initial_title,
        "created_at": time.time(),
        "messages": [],
    }
    if "sessions" not in st.session_state:
        st.session_state.sessions = {}
    st.session_state.sessions[session_id] = new_session
    save_all_sessions(st.session_state.sessions)
    return session_id


def delete_session(session_id: str) -> None:
    if session_id in st.session_state.sessions:
        del st.session_state.sessions[session_id]
        save_all_sessions(st.session_state.sessions)
        if st.session_state.active_session_id == session_id:
            if st.session_state.sessions:
                sorted_keys = sorted(
                    st.session_state.sessions.keys(),
                    key=lambda k: st.session_state.sessions[k].get("created_at", 0),
                    reverse=True,
                )
                st.session_state.active_session_id = sorted_keys[0]
            else:
                st.session_state.active_session_id = create_new_session()
        st.rerun()


init_session_state()
active_session = st.session_state.sessions.get(st.session_state.active_session_id)
if not active_session:
    new_id = create_new_session()
    st.session_state.active_session_id = new_id
    active_session = st.session_state.sessions[new_id]

# -----------------------------------------------------------------------------
# SIDEBAR: Conversation History, Document Manager & Settings
# -----------------------------------------------------------------------------
with st.sidebar:
    # 1. New Chat Action
    if st.button("➕  New Chat", use_container_width=True, type="primary"):
        new_id = create_new_session()
        st.session_state.active_session_id = new_id
        st.rerun()

    st.markdown("---")

    # 2. Conversation History List
    st.subheader("🕒 Conversation History")
    all_sessions = st.session_state.sessions

    if all_sessions:
        sorted_sessions = sorted(
            all_sessions.values(),
            key=lambda s: s.get("created_at", 0),
            reverse=True,
        )
        for s in sorted_sessions:
            s_id = s["id"]
            title = s.get("title", "Conversation")
            is_active = s_id == st.session_state.active_session_id

            col_btn, col_del = st.columns([5, 1])
            with col_btn:
                btn_label = f"💬 {title}" if not is_active else f"▶️ {title}"
                if st.button(
                    btn_label,
                    key=f"sess_{s_id}",
                    use_container_width=True,
                    disabled=is_active,
                ):
                    st.session_state.active_session_id = s_id
                    st.rerun()
            with col_del:
                if st.button("🗑️", key=f"del_{s_id}", help="Delete chat"):
                    delete_session(s_id)
    else:
        st.caption("No previous conversations yet.")

    st.markdown("---")

    # 3. Document Management
    with st.expander("📄 Document Manager", expanded=False):
        uploaded_file = st.file_uploader(
            "Upload PDF to Knowledge Base",
            type=["pdf"],
            accept_multiple_files=False,
            key="pdf_uploader",
        )
        if uploaded_file is not None:
            file_path = UPLOADS_DIR / uploaded_file.name
            if not file_path.exists():
                file_path.write_bytes(uploaded_file.getbuffer())
                with st.spinner(f"Ingesting {uploaded_file.name}..."):
                    asyncio.run(send_rag_ingest_event(file_path))
                    time.sleep(0.5)
                st.success(f"Ingestion dispatched: {uploaded_file.name}")
            else:
                st.info(f"File already stored: {uploaded_file.name}")

        existing_pdfs = list(UPLOADS_DIR.glob("*.pdf"))
        if existing_pdfs:
            st.markdown(f"**Indexed Documents ({len(existing_pdfs)}):**")
            for pdf in existing_pdfs:
                st.caption(f"• `{pdf.name}`")
        else:
            st.caption("No PDFs uploaded yet.")

    # 4. Settings & Model Configuration
    with st.expander("⚙️ Settings & Configuration", expanded=False):
        selected_model_label = st.selectbox(
            "Primary Model Strategy",
            options=list(MODEL_OPTIONS.keys()),
            index=0,
            help="Choose the primary model or allow the auto-priority cascade to failover gracefully.",
        )
        selected_model = MODEL_OPTIONS[selected_model_label]

        top_k = st.slider(
            "Chunks to Retrieve (top_k)",
            min_value=1,
            max_value=20,
            value=5,
            step=1,
            help="Number of most similar semantic context chunks retrieved from Qdrant.",
        )

        st.markdown("**Distributed Fallback Sequence:**")
        st.caption("1. 🥇 Google Gemini 2.5 Flash (~1.8s)")
        st.caption("2. 🥈 Qwen 2.5 72B Instruct (~2.5s)")
        st.caption("3. 🥉 NVIDIA Nemotron 120B (~6.0s)")

    # 5. Service Health Pulse
    with st.expander("🔌 System Health Status", expanded=False):
        health = check_services_health()
        for svc_name, is_ok in health.items():
            if is_ok:
                st.markdown(f"🟢 **{svc_name}**: Online")
            else:
                st.markdown(f"🔴 **{svc_name}**: Offline")

# -----------------------------------------------------------------------------
# MAIN CHAT AREA: Message Stream & Pinned Bottom Input
# -----------------------------------------------------------------------------
# Chat Header
col_header, col_badge = st.columns([3, 1])
with col_header:
    st.title("🤖 Document AI Assistant")
    st.caption("Conversational RAG powered by Inngest, Qdrant & Distributed Multi-Model Fallbacks")
with col_badge:
    model_tag = selected_model_label.split(" (")[0]
    st.markdown(f"<div style='text-align: right; padding-top: 15px;'><code>{model_tag}</code></div>", unsafe_allow_html=True)

# Render Message Stream
messages = active_session.get("messages", [])

if not messages:
    # Empty State Welcome Hero
    st.markdown("### 👋 Welcome to your Document Assistant!")
    st.info(
        "Upload a PDF in the **Document Manager** on the left, or start asking questions about existing documents below.\n\n"
        "**Example queries you can try:**\n"
        "- *What are the core findings or key takeaways of the document?*\n"
        "- *Summarize the methodology and technical architecture.*\n"
        "- *Extract all dates, milestones, and deliverables.*"
    )
else:
    for msg in messages:
        role = msg["role"]
        avatar = "👤" if role == "user" else "🤖"
        with st.chat_message(role, avatar=avatar):
            st.markdown(msg["content"])

            if role == "assistant":
                # Latency & Model Telemetry Badge
                model_used = msg.get("model_used")
                latency_ms = msg.get("latency_ms")
                if model_used:
                    latency_str = f" in {latency_ms / 1000:.2f}s" if latency_ms else ""
                    st.caption(f"⚡ *Answered by `{model_used}`{latency_str}*")

                # Fallback Warning Banner
                fallback_history = msg.get("fallback_history", [])
                if fallback_history:
                    st.warning(
                        f"⚠️ **Automatic Failover:** Primary tier failed. Successfully recovered via `{model_used}`."
                    )
                    with st.expander("View Failover Trace"):
                        for f_item in fallback_history:
                            st.write(
                                f"- ❌ `{f_item.get('model')}` failed: {f_item.get('error')} ({f_item.get('latency_ms', 0):.0f}ms)"
                            )

                # Sources & Citations
                sources = msg.get("sources", [])
                if sources:
                    with st.expander(f"📚 Sources & Citations ({len(sources)})"):
                        for s in sources:
                            st.markdown(f"- 📄 `{s}`")

# -----------------------------------------------------------------------------
# PINNED FIXED BOTTOM INPUT BAR (st.chat_input)
# -----------------------------------------------------------------------------
user_query = st.chat_input("Ask a question about your documents...")

if user_query and user_query.strip():
    clean_query = user_query.strip()

    # 1. Update session title if this is the first user query
    if not messages or active_session.get("title") == "New Conversation":
        snippet = clean_query[:32] + ("..." if len(clean_query) > 32 else "")
        active_session["title"] = snippet

    # 2. Append & display User Message immediately
    user_msg_entry = {
        "role": "user",
        "content": clean_query,
        "timestamp": time.time(),
    }
    active_session["messages"].append(user_msg_entry)
    save_all_sessions(st.session_state.sessions)

    with st.chat_message("user", avatar="👤"):
        st.markdown(clean_query)

    # 3. Generate Assistant Response
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Searching semantic context & dispatching multi-model workflow..."):
            try:
                event_id = asyncio.run(
                    send_rag_query_event(
                        question=clean_query,
                        top_k=int(top_k),
                        model=selected_model,
                    )
                )
                output = wait_for_run_output(event_id)
                answer = output.get("answer", "(No answer generated)")
                sources = output.get("sources", [])
                model_used = output.get("model_used", "Unknown")
                latency_ms = output.get("latency_ms", 0)
                fallback_history = output.get("fallback_history", [])

                # Render Answer & Badges
                st.markdown(answer)

                if model_used:
                    latency_str = f" in {latency_ms / 1000:.2f}s" if latency_ms else ""
                    st.caption(f"⚡ *Answered by `{model_used}`{latency_str}*")

                if fallback_history:
                    st.warning(
                        f"⚠️ **Automatic Failover:** Primary tier failed. Successfully recovered via `{model_used}`."
                    )
                    with st.expander("View Failover Trace"):
                        for f_item in fallback_history:
                            st.write(
                                f"- ❌ `{f_item.get('model')}` failed: {f_item.get('error')} ({f_item.get('latency_ms', 0):.0f}ms)"
                            )

                if sources:
                    with st.expander(f"📚 Sources & Citations ({len(sources)})"):
                        for s in sources:
                            st.markdown(f"- 📄 `{s}`")

                # 4. Save Assistant Response to persistent history
                assistant_msg_entry = {
                    "role": "assistant",
                    "content": answer,
                    "model_used": model_used,
                    "latency_ms": latency_ms,
                    "sources": sources,
                    "fallback_history": fallback_history,
                    "timestamp": time.time(),
                }
                active_session["messages"].append(assistant_msg_entry)
                save_all_sessions(st.session_state.sessions)

            except Exception as e:
                error_text = f"An error occurred while generating the answer: `{e}`"
                st.error(error_text)
                active_session["messages"].append({
                    "role": "assistant",
                    "content": error_text,
                    "timestamp": time.time(),
                })
                save_all_sessions(st.session_state.sessions)

    # Rerun to cleanly update sidebar titles and active state
    st.rerun()
