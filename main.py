import asyncio
import datetime
import json
import logging
import os
from pathlib import Path
import re
import shutil
import time
import uuid

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
import inngest
import inngest.fast_api
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import (
    AuthResponse,
    IdentityContext,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
    create_jwt,
    get_security_context,
    hash_password,
    require_admin,
    require_authenticated,
    verify_password,
)
from custom_types import RAGChunkAndSrc, RAGSearchResult, RAGUpsertResult
from data_loader import (
    embed_texts,
    load_and_chunk_pdf,
    load_and_chunk_pdf_with_metadata,
    load_and_chunk_document,
    load_and_chunk_document_with_metadata,
)
from database import ChatHistory, GuestSession, User, UserProfile, get_db, init_db, SessionLocal
from vector_db import QdrantStorage

load_dotenv()

# Allowed document formats across the platform (PDF, Word, Text)
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}

# -----------------------------------------------------------------------------
# Configuration & Inngest Client
# -----------------------------------------------------------------------------
logger = logging.getLogger("uvicorn")

INNGEST_SIGNING_KEY = os.getenv("INNGEST_SIGNING_KEY")
INNGEST_EVENT_KEY = os.getenv("INNGEST_EVENT_KEY")
IS_PRODUCTION = bool(INNGEST_SIGNING_KEY)

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logger,
    is_production=IS_PRODUCTION,
    signing_key=INNGEST_SIGNING_KEY,
    event_key=INNGEST_EVENT_KEY,
    serializer=inngest.PydanticSerializer(),
)

UPLOADS_BASE_DIR = Path("uploads")
UPLOADS_BASE_DIR.mkdir(parents=True, exist_ok=True)


def get_owner_storage_dir(owner_id: str) -> Path:
    """Returns the isolated filesystem namespace for a given user or guest."""
    prefix = "users" if owner_id.startswith("usr_") else "guests"
    path = UPLOADS_BASE_DIR / prefix / owner_id
    path.mkdir(parents=True, exist_ok=True)
    return path


# -----------------------------------------------------------------------------
# Bootstrap Default Admin Account
# -----------------------------------------------------------------------------
def bootstrap_default_admin():
    """Initializes database tables and creates a default admin account if none exists."""
    init_db()
    db = SessionLocal()
    try:
        admin_exists = db.query(User).filter(User.role == "admin").first()
        if not admin_exists:
            admin_email = os.getenv("ADMIN_EMAIL", "admin@askfiles.ai")
            admin_pwd = os.getenv("ADMIN_PASSWORD", "AdminPass123!")
            admin_name = os.getenv("ADMIN_NAME", "System Administrator")
            admin_user = User(
                id=f"usr_admin_{uuid.uuid4().hex[:8]}",
                email=admin_email,
                password_hash=hash_password(admin_pwd),
                name=admin_name,
                role="admin",
                created_at=datetime.datetime.now(datetime.timezone.utc),
            )
            db.add(admin_user)
            db.commit()
            logger.info(f"Initialized default administrator account: {admin_email}")
    except Exception as e:
        logger.warning(f"Admin bootstrap check notice: {e}")
        db.rollback()
    finally:
        db.close()


# -----------------------------------------------------------------------------
# Pydantic Schemas for REST API
# -----------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question about the ingested documents")
    top_k: int = Field(5, ge=1, le=20, description="Number of context chunks to retrieve")
    model: str | None = Field(None, description="Optional primary model override")
    session_key: str | None = Field(None, description="Frontend chat session ID for episodic tracking")
    selected_sources: list[str] | None = Field(None, description="Optional list of source filenames to restrict retrieval to (Selective Grounding)")


class FallbackAttempt(BaseModel):
    model: str
    model_name: str
    error: str | None = None
    latency_ms: float = 0.0


class ContextChunkItem(BaseModel):
    id: int
    source: str
    page: int | str | None = None
    section: str | None = None
    text: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    model_used: str
    latency_ms: float
    fallback_history: list[FallbackAttempt] = []
    num_contexts: int
    context_chunks: list[ContextChunkItem] = []
    suggested_followups: list[str] = []
    intent: str = "document_query"


class DocumentInfo(BaseModel):
    filename: str
    size_bytes: int
    modified_at: float


# -----------------------------------------------------------------------------
# NotebookLM-Style Intent Classification
# -----------------------------------------------------------------------------
GREETING_PATTERNS = [
    r"^\s*(hi|hello|hey|hiya|howdy|greetings|good\s+(morning|afternoon|evening|day)|sup|yo)\b",
    r"^\s*(who\s+are\s+you|what\s+is\s+your\s+name)\b",
]

HELP_PATTERNS = [
    r"^\s*(help|help\s+me|what\s+can\s+you\s+do|how\s+does\s+this\s+work|features|instructions|guide\s+me)\b",
    r"^\s*(what\s+should\s+i\s+ask|how\s+to\s+use)\b",
]


def classify_user_intent(question: str) -> str:
    cleaned = question.strip().lower()
    for pattern in GREETING_PATTERNS:
        if re.search(pattern, cleaned):
            return "greeting"
    for pattern in HELP_PATTERNS:
        if re.search(pattern, cleaned):
            return "help"
    return "document_query"


# -----------------------------------------------------------------------------
# Model Fallback Chain Resolver
# -----------------------------------------------------------------------------
def get_fallback_models(requested_model: str | None = None) -> list[tuple[str, str, str]]:
    default_chain = [
        ("gemini-flash", "google/gemini-2.5-flash", "Google Gemini 2.5 Flash"),
        ("qwen-72b", "qwen/qwen-2.5-72b-instruct", "Qwen 2.5 72B Instruct"),
        ("nemotron-120b", "nvidia/nemotron-3-super-120b-a12b:free", "NVIDIA Nemotron 120B"),
    ]
    raw = os.getenv("MODEL_FALLBACK_CHAIN", "")
    if raw.strip():
        models = [m.strip() for m in raw.split(",") if m.strip()]
        chain = []
        name_map = {
            "google/gemini-2.5-flash": "Google Gemini 2.5 Flash",
            "qwen/qwen-2.5-72b-instruct": "Qwen 2.5 72B Instruct",
            "nvidia/nemotron-3-super-120b-a12b:free": "NVIDIA Nemotron 120B",
        }
        for m in models:
            step_key = m.replace("/", "-").replace(":", "-").replace(".", "-")[:20]
            display_name = name_map.get(m, m)
            chain.append((step_key, m, display_name))
    else:
        chain = default_chain

    if requested_model and requested_model != "auto":
        chain = [c for c in chain if c[1] == requested_model] + [c for c in chain if c[1] != requested_model]
        if not any(c[1] == requested_model for c in chain):
            step_key = requested_model.replace("/", "-").replace(":", "-").replace(".", "-")[:20]
            chain.insert(0, (step_key, requested_model, requested_model))
    return chain


# -----------------------------------------------------------------------------
# Core RAG Ingestion Function (Tenant Partitioned, Multi-Format)
# -----------------------------------------------------------------------------
def process_and_ingest_document(doc_path: str, source_id: str | None = None, owner_id: str | None = None) -> int:
    source_id = source_id or Path(doc_path).name
    owner_id = owner_id or "system"
    chunks_meta = load_and_chunk_document_with_metadata(doc_path)
    if not chunks_meta:
        return 0

    texts = [c["text"] for c in chunks_meta]
    vecs = embed_texts(texts)
    ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{owner_id}:{source_id}:{i}")) for i in range(len(chunks_meta))]
    payloads = [
        {
            "owner_id": owner_id,
            "source": source_id,
            "text": chunks_meta[i]["text"],
            "page": chunks_meta[i].get("page", "1"),
            "section": chunks_meta[i].get("section", ""),
        }
        for i in range(len(chunks_meta))
    ]
    QdrantStorage().upsert(ids, vecs, payloads)
    return len(chunks_meta)


# Backward compatibility alias
process_and_ingest_pdf = process_and_ingest_document


# -----------------------------------------------------------------------------
# Core Query & Multi-Tier Fallback Cascade Engine (Tenant Isolated & Memory-Aware)
# -----------------------------------------------------------------------------
def execute_query_cascade(
    question: str,
    owner_id: str,
    top_k: int = 5,
    requested_model: str | None = None,
    session_key: str | None = None,
    selected_sources: list[str] | None = None,
) -> dict:
    owner_dir = get_owner_storage_dir(owner_id)
    available_files = [
        f.name for f in owner_dir.iterdir()
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
    ]

    intent = classify_user_intent(question)

    # 1. Handle Conversational Greeting Intent (NotebookLM Standard)
    if intent == "greeting":
        if available_files:
            file_list_str = ", ".join(f"`{f}`" for f in available_files[:3])
            if len(available_files) > 3:
                file_list_str += f" and {len(available_files) - 3} more"
            return {
                "answer": f"Hello! I am **AskFiles AI**, grounded in your uploaded documents ({file_list_str}).\n\nI can answer specific questions, synthesize cross-document themes, or generate executive summaries and study guides with interactive page citations.\n\nWhat would you like to explore?",
                "sources": [],
                "num_contexts": 0,
                "model_used": "system (greeting router)",
                "latency_ms": 1.0,
                "fallback_history": [],
                "context_chunks": [],
                "suggested_followups": [
                    "Give me an executive summary of my documents",
                    "What are the key findings or data points?",
                    "What methodology or approach is used?",
                ],
                "intent": "greeting",
            }
        else:
            return {
                "answer": "Hello! Welcome to **AskFiles AI**.\n\nPlease upload a document (PDF, Word DOCX, or Text) using the sidebar or upload zone to get started. Once uploaded, I will index its content so you can ask questions, extract key findings, and verify assertions with interactive page and section citations.",
                "sources": [],
                "num_contexts": 0,
                "model_used": "system (greeting router)",
                "latency_ms": 1.0,
                "fallback_history": [],
                "context_chunks": [],
                "suggested_followups": [
                    "How do I upload a document?",
                    "What file formats are supported?",
                    "How does multi-tenant data privacy work?",
                ],
                "intent": "greeting",
            }

    # 2. Handle Help / Capabilities Intent (NotebookLM Standard)
    if intent == "help":
        active_str = f"your **{len(available_files)} active document(s)**" if available_files else "your documents (upload one to begin)"
        return {
            "answer": (
                f"### What AskFiles AI Can Do With {active_str}:\n\n"
                "• **Factual Question Answering**: Query anything in your files and receive answers grounded strictly in source passages, accompanied by interactive numeric citation badges (`[1]`, `[2]`).\n"
                "• **Selective Document Grounding**: Use the checkboxes next to each document in the sidebar to isolate specific papers or search across your entire collection.\n"
                "• **Interactive Verification**: Hover or click any citation pill to view the exact excerpt and page location directly from the PDF.\n"
                "• **Synthesis & Summarization**: Ask for high-level briefings, comparative analyses, or structured FAQs.\n"
                "• **Cognitive Memory**: Seamless multi-turn continuity (Episodic Memory) and automated background interest distillation (Semantic Memory).\n\n"
                "Try clicking one of the suggested prompts below to start exploring!"
            ),
            "sources": [],
            "num_contexts": 0,
            "model_used": "system (help router)",
            "latency_ms": 1.0,
            "fallback_history": [],
            "context_chunks": [],
            "suggested_followups": [
                "Summarize the central thesis or conclusion",
                "Extract the top 5 key takeaways in bullet points",
                "Are there any limitations or open challenges discussed?",
            ],
            "intent": "help",
        }

    # 3. Document Retrieval via Qdrant with Selective Grounding Filter
    store = QdrantStorage()
    query_vec = embed_texts([question])[0]

    # Search strictly filtered to this owner's vectors (and optional selective sources)
    found = store.search(
        query_vec,
        owner_id=owner_id,
        top_k=top_k,
        sources_filter=selected_sources,
    )

    # If the user/guest has uploaded no documents in their namespace:
    if not found["contexts"]:
        if not available_files:
            return {
                "answer": "You haven't uploaded any documents in this session yet. Please upload a document (PDF, Word DOCX, or Text) first so I can analyze, summarize, or extract insights with citations for you.",
                "sources": [],
                "num_contexts": 0,
                "model_used": "system",
                "latency_ms": 2.0,
                "fallback_history": [],
                "context_chunks": [],
                "suggested_followups": ["How do I upload a document?"],
                "intent": "out_of_domain",
            }
        else:
            filter_note = f" among your {len(selected_sources)} selected document(s)" if selected_sources else ""
            return {
                "answer": f"The provided documents{filter_note} do not contain relevant information regarding this query.\n\nAskFiles strictly adheres to a **Zero-External-Hallucination Policy**—I am grounded exclusively in your active documents and do not invent facts outside of them.\n\nPlease try rephrasing your question or selecting additional sources in the sidebar.",
                "sources": [],
                "num_contexts": 0,
                "model_used": "system (grounding guardrail)",
                "latency_ms": 2.0,
                "fallback_history": [],
                "context_chunks": [],
                "suggested_followups": [
                    "What topics are covered in my documents?",
                    "Provide a general overview of the uploaded files",
                ],
                "intent": "out_of_domain",
            }

    # -------------------------------------------------------------------------
    # Episodic Memory: Working Context Injection (Sean Chen's Memory Architecture)
    # -------------------------------------------------------------------------
    history_block = ""
    try:
        db = SessionLocal()
        query = db.query(ChatHistory).filter(ChatHistory.owner_id == owner_id)
        if session_key:
            query = query.filter(ChatHistory.session_key == session_key)
        recent_turns = query.order_by(ChatHistory.created_at.desc()).limit(6).all()
        db.close()

        if recent_turns:
            chronological = list(reversed(recent_turns))
            history_lines = []
            for t in chronological:
                ans_snippet = t.answer[:300] + "..." if len(t.answer) > 300 else t.answer
                history_lines.append(f"User: {t.question}\nAssistant: {ans_snippet}")
            history_block = "\n\n".join(history_lines)
    except Exception as e:
        logger.warning(f"Failed to fetch episodic chat history for working memory: {e}")

    # -------------------------------------------------------------------------
    # Semantic Memory: Distilled User Profile Context (Phase 6)
    # -------------------------------------------------------------------------
    profile_block = ""
    try:
        db = SessionLocal()
        user_prof = db.query(UserProfile).filter(UserProfile.owner_id == owner_id).first()
        db.close()
        if user_prof and user_prof.summary:
            profile_block = f"User Profile & Expertise Context:\n- Summary: {user_prof.summary}\n"
            if user_prof.interests:
                try:
                    ints = json.loads(user_prof.interests)
                    if ints:
                        profile_block += f"- Key Focus Areas: {', '.join(ints)}\n"
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Failed to fetch user semantic profile: {e}")

    context_block = "\n\n".join(f"- {c}" for c in found["contexts"])
    system_prompt = (
        "You are AskFiles AI, a precise, intelligent, and grounded document assistant adhering to academic research standards.\n"
        "You have access to both Semantic User Profile memory and Episodic Conversation history to tailor explanations and maintain multi-turn continuity.\n"
        "MANDATORY CITATION RULES:\n"
        "1. After EVERY piece of information, claim, finding, or sentence you state from the document, you MUST append an inline numeric citation in brackets: [1], [2], [3], etc., citing the corresponding numbered context chunk (e.g. 'Support Vector Machines maximize the street width between opposite classes [1].').\n"
        "2. If multiple source chunks support a statement, combine them such as [1][2] or [1, 2].\n"
        "3. Use ONLY numeric reference markers like [1], [2], [3]. NEVER write document filenames, page numbers, section titles, or strings like [Source: ...], [data_engineering.pdf, Page 424] in the response body. All metadata will be rendered in interactive popovers and the References layer automatically.\n"
        "4. Always attach the citation brackets directly to the fact or sentence without extraneous spaces before periods (e.g., write 'reliable log [1].' NEVER write 'reliable log [1] .').\n"
        "5. Rely ONLY on the provided context chunks. If the context does not answer the question, state that clearly."
    )

    conversation_prefix = ""
    if profile_block:
        conversation_prefix += f"{profile_block}\n"
    if history_block:
        conversation_prefix += f"Recent Conversation Context (Episodic Memory):\n{history_block}\n\n---\n\n"

    user_content = (
        f"{conversation_prefix}"
        f"Referenced Document Chunks:\n\n{context_block}\n\n"
        f"User Question: {question}\n\n"
        "Provide a grounded, comprehensive answer. Cite every fact using strictly numeric brackets like [1], [2] corresponding to the source numbers above. Never write filenames or page numbers in brackets in the body text."
    )

    openrouter_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    openrouter_base_url = os.getenv("OPENROUTER_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    client = OpenAI(
        base_url=openrouter_base_url,
        api_key=openrouter_key,
        timeout=30.0,
    )

    models_to_try = get_fallback_models(requested_model)
    answer = None
    model_used = None
    latency_ms = 0.0
    fallback_history = []

    for _, model_id, display_name in models_to_try:
        t0 = time.time()
        try:
            res = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=1024,
                temperature=0.2,
            )
            dt = (time.time() - t0) * 1000
            msg = res.choices[0].message
            text = (msg.content or getattr(msg, "reasoning", "") or "").strip()
            if not text:
                raise ValueError(f"Model {model_id} returned empty response")

            answer = text
            model_used = model_id
            latency_ms = round(dt, 2)
            break

        except Exception as e:
            dt = (time.time() - t0) * 1000
            logger.warning(f"Distributed fallback: Model {model_id} failed in {dt:.0f}ms: {e}")
            fallback_history.append({
                "model": model_id,
                "model_name": display_name,
                "error": str(e),
                "latency_ms": round(dt, 2),
            })

    if not answer:
        raise RuntimeError(f"All distributed LLM fallback models failed: {fallback_history}")

    return {
        "answer": answer,
        "sources": found["sources"],
        "num_contexts": len(found["contexts"]),
        "model_used": model_used or "Unknown",
        "latency_ms": latency_ms,
        "fallback_history": fallback_history,
        "context_chunks": found.get("context_chunks", []),
        "suggested_followups": [
            "Can you elaborate on this point with more detail?",
            "What specific data or evidence supports this conclusion?",
            "Summarize the key takeaways into bullet points",
        ],
        "intent": "document_query",
    }


# -----------------------------------------------------------------------------
# Inngest Background Workflows
# -----------------------------------------------------------------------------
@inngest_client.create_function(
    fn_id="RAG: Ingest PDF",
    trigger=inngest.TriggerEvent(event="rag/ingest_pdf"),
    throttle=inngest.Throttle(limit=2, period=datetime.timedelta(minutes=1)),
    rate_limit=inngest.RateLimit(limit=1, period=datetime.timedelta(hours=4), key="event.data.source_id"),
)
async def rag_ingest_pdf(ctx: inngest.Context):
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        doc_path = ctx.event.data.get("doc_path") or ctx.event.data.get("pdf_path")
        source_id = ctx.event.data.get("source_id", doc_path)
        chunks = load_and_chunk_document(doc_path)
        return RAGChunkAndSrc(chunks=chunks, source_id=source_id)

    def _upsert(chunks_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        chunks = chunks_and_src.chunks
        source_id = chunks_and_src.source_id
        owner_id = ctx.event.data.get("owner_id", "system")
        vecs = embed_texts(chunks)
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{owner_id}:{source_id}:{i}")) for i in range(len(chunks))]
        payloads = [{"owner_id": owner_id, "source": source_id, "text": chunks[i]} for i in range(len(chunks))]
        QdrantStorage().upsert(ids, vecs, payloads)
        return RAGUpsertResult(ingested=len(chunks))

    chunks_and_src = await ctx.step.run("load-and-chunk", lambda: _load(ctx), output_type=RAGChunkAndSrc)
    ingested = await ctx.step.run("embed-and-upsert", lambda: _upsert(chunks_and_src), output_type=RAGUpsertResult)
    return ingested.model_dump()


@inngest_client.create_function(
    fn_id="RAG: Query PDF",
    trigger=inngest.TriggerEvent(event="rag/query_pdf_ai"),
)
async def rag_query_pdf_ai(ctx: inngest.Context):
    question = ctx.event.data["question"]
    owner_id = ctx.event.data.get("owner_id", "system")
    top_k = int(ctx.event.data.get("top_k", 5))
    requested_model = ctx.event.data.get("model")

    result = await ctx.step.run(
        "execute-rag-cascade",
        lambda: execute_query_cascade(question, owner_id, top_k, requested_model),
    )
    return result


# -----------------------------------------------------------------------------
# Sean Chen Semantic Memory Consolidation Engine (Phase 6)
# -----------------------------------------------------------------------------
def distill_semantic_profile(turns_data: list[dict]) -> dict:
    """
    Cognitive memory distillation:
    Extracts durable user facts, domain expertise, and core research interests using LLM.
    """
    if not turns_data:
        return {"summary": "", "interests": []}

    dialogue = "\n".join([f"Q: {t['question']}\nA: {t['answer']}" for t in turns_data])
    prompt = (
        "You are an AI Memory Consolidation Engine following the cognitive architecture of human working and semantic memory.\n"
        "Analyze the following recent conversation history between the user and assistant.\n"
        "Extract and distill:\n"
        "1. A concise, factual summary (2-3 sentences) characterizing the user's domain focus, key interests, questions, and research/technical preferences.\n"
        "2. A JSON array of 3-5 core topical keywords.\n\n"
        f"User Conversation Turns:\n{dialogue}\n\n"
        "Respond STRICTLY in JSON format with keys 'summary' and 'interests'. Example:\n"
        '{"summary": "The user is researching distributed streaming systems, focusing on Apache Kafka partition strategies and vector databases.", "interests": ["Distributed Systems", "Kafka", "Vector DB"]}'
    )
    openrouter_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    openrouter_base_url = os.getenv("OPENROUTER_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    client = OpenAI(base_url=openrouter_base_url, api_key=openrouter_key, timeout=30.0)

    models_to_try = [
        "google/gemini-2.5-flash",
        "qwen/qwen-2.5-72b-instruct",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ]

    for model_id in models_to_try:
        try:
            res = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.1,
            )
            raw = (res.choices[0].message.content or "").strip()
            if not raw:
                continue
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(raw)
            if "summary" in data and "interests" in data:
                return data
        except Exception as e:
            logger.warning(f"Distillation attempt failed on {model_id}: {e}")
            continue

    return {
        "summary": "User actively researches uploaded document topics.",
        "interests": ["Document Analysis", "Research"],
    }


def consolidate_user_memory(owner_id: str, turn_count: int | None = None) -> dict:
    """
    Sean Chen Cognitive Memory Consolidation:
    Fetches recent episodic turns, distills durable user profile summary and interests via LLM,
    and updates the user_profiles table in Neon PostgreSQL.
    """
    db = SessionLocal()
    try:
        turns = (
            db.query(ChatHistory)
            .filter(ChatHistory.owner_id == owner_id)
            .order_by(ChatHistory.created_at.desc())
            .limit(15)
            .all()
        )
        if not turns:
            return {"summary": "", "interests": [], "turn_count": 0}

        actual_turn_count = turn_count if turn_count is not None else len(turns)
        turns_data = [{"question": t.question, "answer": t.answer[:250]} for t in reversed(turns)]

        distilled = distill_semantic_profile(turns_data)

        prof = db.query(UserProfile).filter(UserProfile.owner_id == owner_id).first()
        now = datetime.datetime.now(datetime.timezone.utc)
        summary_text = distilled.get("summary", "")
        interests_json = json.dumps(distilled.get("interests", []))

        if not prof:
            prof = UserProfile(
                owner_id=owner_id,
                summary=summary_text,
                interests=interests_json,
                last_consolidated=now,
                turn_count_at_last=actual_turn_count,
            )
            db.add(prof)
        else:
            prof.summary = summary_text
            prof.interests = interests_json
            prof.last_consolidated = now
            prof.turn_count_at_last = actual_turn_count

        db.commit()
        db.refresh(prof)
        logger.info(f"Consolidated semantic memory profile for user {owner_id} ({actual_turn_count} turns)")
        return prof.to_dict()
    except Exception as e:
        logger.error(f"Error in consolidate_user_memory for {owner_id}: {e}")
        db.rollback()
        return {"summary": "", "interests": [], "error": str(e)}
    finally:
        db.close()


@inngest_client.create_function(
    fn_id="RAG: Consolidate Memory",
    trigger=inngest.TriggerEvent(event="rag/consolidate_memory"),
    throttle=inngest.Throttle(limit=2, period=datetime.timedelta(minutes=1)),
)
async def rag_consolidate_memory(ctx: inngest.Context):
    """
    Sean Chen's Memory Consolidation Gate (Inngest Workflow):
    Distills episodic conversation history into high-level semantic user profiles across 3 steps.
    """
    owner_id = ctx.event.data["owner_id"]
    turn_count = ctx.event.data.get("turn_count", 0)

    def _fetch_history():
        db = SessionLocal()
        turns = (
            db.query(ChatHistory)
            .filter(ChatHistory.owner_id == owner_id)
            .order_by(ChatHistory.created_at.desc())
            .limit(15)
            .all()
        )
        db.close()
        return [{"question": t.question, "answer": t.answer[:250]} for t in reversed(turns)]

    turns_data = await ctx.step.run("fetch-episodic-turns", _fetch_history)
    distilled = await ctx.step.run("distill-semantic-profile", lambda: distill_semantic_profile(turns_data))

    def _save():
        db = SessionLocal()
        prof = db.query(UserProfile).filter(UserProfile.owner_id == owner_id).first()
        now = datetime.datetime.now(datetime.timezone.utc)
        summary_text = distilled.get("summary", "")
        interests_json = json.dumps(distilled.get("interests", []))
        if not prof:
            prof = UserProfile(
                owner_id=owner_id,
                summary=summary_text,
                interests=interests_json,
                last_consolidated=now,
                turn_count_at_last=turn_count,
            )
            db.add(prof)
        else:
            prof.summary = summary_text
            prof.interests = interests_json
            prof.last_consolidated = now
            prof.turn_count_at_last = turn_count
        db.commit()
        db.close()
        return {"status": "saved", "owner_id": owner_id, "turn_count": turn_count}

    result = await ctx.step.run("persist-semantic-profile", _save)
    return result


# -----------------------------------------------------------------------------
# Ephemeral Guest Session TTL Reaper (Phase 5)
# -----------------------------------------------------------------------------
def purge_expired_guest_sessions(max_age_hours: int = 2) -> int:
    """
    Deletes all temporary vectors, uploaded PDFs, and chat records
    for guest sessions that have been idle for more than `max_age_hours`.
    """
    db = SessionLocal()
    purged_count = 0
    try:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=max_age_hours)
        expired = db.query(GuestSession).filter(GuestSession.last_seen < cutoff).all()

        store = QdrantStorage()
        for g in expired:
            sid = g.session_id
            # 1. Wipe vectors from Qdrant Cloud
            store.delete_all_for_owner(sid)
            # 2. Delete temporary uploads directory from filesystem
            guest_dir = get_owner_storage_dir(sid)
            if guest_dir.exists():
                shutil.rmtree(guest_dir, ignore_errors=True)
            # 3. Delete temporary episodic chat history
            db.query(ChatHistory).filter(ChatHistory.owner_id == sid).delete()
            # 4. Remove session tracker
            db.delete(g)
            purged_count += 1

        db.commit()
        if purged_count > 0:
            logger.info(f"[TTL Reaper] Purged {purged_count} expired guest sessions older than {max_age_hours}h.")
    except Exception as e:
        logger.error(f"[TTL Reaper] Error executing guest session purge: {e}")
        db.rollback()
    finally:
        db.close()

    return purged_count


@inngest_client.create_function(
    fn_id="Maintenance: Ephemeral TTL Reaper",
    trigger=inngest.TriggerCron(cron="*/30 * * * *"),
)
async def rag_ttl_reaper(ctx: inngest.Context):
    """
    Phase 5 TTL Reaper (Inngest Periodic Cron Workflow):
    Runs every 30 minutes to enforce strict storage bounds by purging idle guest data.
    """
    purged = await ctx.step.run(
        "purge-idle-guests",
        lambda: purge_expired_guest_sessions(max_age_hours=2),
    )
    return {"status": "success", "purged_guest_sessions": purged, "max_age_hours": 2}


async def guest_reaper_loop():
    """Periodic background daemon running every 30 minutes to enforce ephemeral storage bounds."""
    while True:
        try:
            await asyncio.sleep(1800)  # 30 minutes
            await asyncio.to_thread(purge_expired_guest_sessions, 2)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[TTL Reaper Loop] Unexpected error: {e}")
            await asyncio.sleep(60)


# -----------------------------------------------------------------------------
# FastAPI Application & REST Endpoints
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Conversational Document Assistant API",
    description="Production-grade RAG backend with multi-tenant data isolation, Inngest observability, and Neon PostgreSQL",
    version="2.1.0",
)

# Startup Hook
@app.on_event("startup")
async def on_startup():
    await asyncio.to_thread(bootstrap_default_admin)
    asyncio.create_task(guest_reaper_loop())


# CORS Middleware (Allows Vercel Frontend to communicate with Render Backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.api_route("/health", methods=["GET", "HEAD"])
@app.api_route("/api/health", methods=["GET", "HEAD"])
def health_check():
    return {
        "status": "healthy",
        "service": "Conversational-Document-Assistant",
        "is_production": IS_PRODUCTION,
        "qdrant_cloud": True,
        "neon_postgres": True,
        "inngest_cloud": bool(INNGEST_SIGNING_KEY),
    }


# -----------------------------------------------------------------------------
# Authentication & Authorization Endpoints (Phase 1)
# -----------------------------------------------------------------------------
@app.post("/api/auth/register", response_model=AuthResponse)
def register(req: UserRegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email.lower().strip()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    # Secure role assignment: default to "user" unless configured
    assigned_role = "admin" if req.role == "admin" and not db.query(User).filter(User.role == "admin").first() else "user"

    now = datetime.datetime.now(datetime.timezone.utc)
    new_user = User(
        id=user_id,
        email=req.email.lower().strip(),
        password_hash=hash_password(req.password),
        name=req.name.strip(),
        role=assigned_role,
        created_at=now,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_jwt(new_user.id, new_user.role, new_user.name, new_user.email)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserProfileResponse(**new_user.to_dict()),
    )


@app.post("/api/auth/login", response_model=AuthResponse)
def login(req: UserLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower().strip()).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_jwt(user.id, user.role, user.name, user.email)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserProfileResponse(**user.to_dict()),
    )


@app.get("/api/auth/me", response_model=UserProfileResponse)
def get_current_user_profile(identity: IdentityContext = Depends(require_authenticated), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == identity.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserProfileResponse(**user.to_dict())


@app.post("/api/session/clear")
def clear_session(
    identity: IdentityContext = Depends(get_security_context),
    db: Session = Depends(get_db),
):
    """
    Cleans up all vector points, uploaded PDFs, and chat records
    for the current ephemeral guest session or active user.
    """
    owner_id = identity.id

    # 1. Purge all vector points in Qdrant for this tenant
    QdrantStorage().delete_all_for_owner(owner_id)

    # 2. Delete tenant's filesystem directory
    owner_dir = get_owner_storage_dir(owner_id)
    if owner_dir.exists():
        shutil.rmtree(owner_dir, ignore_errors=True)

    # 3. Delete tenant's episodic chat history
    try:
        db.query(ChatHistory).filter(ChatHistory.owner_id == owner_id).delete()
        if owner_id.startswith("gst_"):
            db.query(GuestSession).filter(GuestSession.session_id == owner_id).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Error purging chat history for {owner_id}: {e}")

    return {
        "status": "success",
        "message": f"Successfully wiped all documents, vectors, and chat history for {owner_id}",
    }


# -----------------------------------------------------------------------------
# Inngest Observability Endpoint (Restricted to Admins Only - Phase 1 RBAC)
# -----------------------------------------------------------------------------
@app.get("/api/inngest/overview")
def inngest_overview(identity: IdentityContext = Depends(require_admin)):
    """
    Privileged observability endpoint.
    Strictly forbidden for guests and regular users.
    """
    return {
        "app_id": "rag_app",
        "mode": "cloud" if IS_PRODUCTION else "development",
        "is_production": IS_PRODUCTION,
        "webhook_path": "/api/inngest",
        "has_signing_key": bool(INNGEST_SIGNING_KEY),
        "has_event_key": bool(INNGEST_EVENT_KEY),
        "dashboard_url": "https://app.inngest.com/",
        "functions": [
            {
                "id": "RAG: Ingest PDF",
                "trigger_event": "rag/ingest_pdf",
                "throttle": "2 runs / 1 minute",
                "rate_limit": "1 run / 4 hours per document",
                "steps": [
                    {
                        "step_id": "load-and-chunk",
                        "title": "Document Parsing & Semantic Chunking",
                        "description": "Extracts text, hierarchy, headings, and page offsets using LlamaIndex PDFReader",
                    },
                    {
                        "step_id": "embed-and-upsert",
                        "title": "Batch Embedding & Qdrant Upsert",
                        "description": "Generates 1536-dim vectors via text-embedding-3-small (batched in 20 chunks) and upserts points to Qdrant Cloud",
                    },
                ],
            },
            {
                "id": "RAG: Query PDF",
                "trigger_event": "rag/query_pdf_ai",
                "throttle": "Unrestricted (Real-time)",
                "rate_limit": "None",
                "steps": [
                    {
                        "step_id": "execute-rag-cascade",
                        "title": "Cosine Retrieval & Multi-Engine Cascade",
                        "description": "Searches top-K vector matches in Qdrant Cloud and queries Google Gemini 2.5 Flash with automatic failover to Qwen 2.5 72B and Nemotron 120B",
                    },
                ],
            },
            {
                "id": "RAG: Consolidate Memory",
                "trigger_event": "rag/consolidate_memory",
                "throttle": "2 runs / 1 minute",
                "rate_limit": "None",
                "steps": [
                    {
                        "step_id": "fetch-conversation-turns",
                        "title": "Episodic History Ingestion",
                        "description": "Retrieves recent episodic conversation turns from Neon PostgreSQL",
                    },
                    {
                        "step_id": "distill-semantic-profile",
                        "title": "LLM Semantic Distillation",
                        "description": "Extracts durable user facts, domain expertise, and research preferences",
                    },
                    {
                        "step_id": "persist-semantic-profile",
                        "title": "Neon Memory Profile Upsert",
                        "description": "Upserts consolidated semantic profile into user_profiles table for instant prompt working memory injection",
                    },
                ],
            },
            {
                "id": "Maintenance: Ephemeral TTL Reaper",
                "trigger_event": "cron(*/30 * * * *)",
                "throttle": "Periodic (Every 30 mins)",
                "rate_limit": "None",
                "steps": [
                    {
                        "step_id": "purge-idle-guests",
                        "title": "Ephemeral Storage Boundary Enforcement",
                        "description": "Purges Qdrant vector points, uploaded PDFs on disk, and chat history for guest sessions inactive for >2 hours",
                    },
                ],
            },
        ],
    }


@app.get("/api/models")
def get_models():
    return {
        "primary": os.getenv("MODEL_PRIMARY", "google/gemini-2.5-flash"),
        "fallback_1": os.getenv("MODEL_FALLBACK_1", "qwen/qwen-2.5-72b-instruct"),
        "fallback_2": os.getenv("MODEL_FALLBACK_2", "nvidia/nemotron-3-super-120b-a12b:free"),
        "models": [
            {"id": "auto", "label": "Auto: Gemini Flash ➜ Qwen 2.5 ➜ Nemotron 120B"},
            {"id": "google/gemini-2.5-flash", "label": "Google Gemini 2.5 Flash (Tier 1 - Low Latency)"},
            {"id": "qwen/qwen-2.5-72b-instruct", "label": "Qwen 2.5 72B Instruct (Tier 2 - Reasoning)"},
            {"id": "nvidia/nemotron-3-super-120b-a12b:free", "label": "NVIDIA Nemotron 120B (Tier 3 - Free Tier)"},
        ],
    }


# -----------------------------------------------------------------------------
# Tenant-Scoped Chat Endpoint (Phase 1 & Phase 2)
# -----------------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    identity: IdentityContext = Depends(get_security_context),
    db: Session = Depends(get_db),
):
    try:
        # 1. Execute grounded RAG query strictly partitioned to the caller's owner_id with Episodic Working Memory & Selective Grounding
        result = await asyncio.to_thread(
            execute_query_cascade,
            req.question,
            identity.id,
            req.top_k,
            req.model,
            req.session_key,
            req.selected_sources,
        )

        # 2. Record episodic chat history turn in Neon PostgreSQL
        try:
            chat_record = ChatHistory(
                owner_id=identity.id,
                session_key=req.session_key,
                question=req.question,
                answer=result["answer"],
                doc_sources=json.dumps(result["sources"]),
                model_used=result["model_used"],
                created_at=datetime.datetime.now(datetime.timezone.utc),
            )
            db.add(chat_record)
            db.commit()
        except Exception as db_err:
            logger.warning(f"Failed to record chat history turn: {db_err}")
            db.rollback()

        # 3. Sean Chen Memory Consolidation Gate (Phase 6):
        # Authenticated users trigger background distillation after accumulating new turns
        if identity.is_authenticated:
            try:
                total_turns = db.query(ChatHistory).filter(ChatHistory.owner_id == identity.id).count()
                prof = db.query(UserProfile).filter(UserProfile.owner_id == identity.id).first()
                last_turn = prof.turn_count_at_last if prof else 0
                if (last_turn == 0 and total_turns >= 3) or (total_turns - last_turn) >= 5:
                    logger.info(f"[Memory Gate] Triggering consolidation for {identity.id} (turns: {total_turns}, last: {last_turn})")
                    asyncio.create_task(asyncio.to_thread(consolidate_user_memory, identity.id, total_turns))
                    asyncio.create_task(
                        inngest_client.send(
                            inngest.Event(
                                name="rag/consolidate_memory",
                                data={
                                    "owner_id": identity.id,
                                    "turn_count": total_turns,
                                },
                            )
                        )
                    )
            except Exception as gate_err:
                logger.warning(f"Failed to check memory consolidation gate: {gate_err}")

        # 4. Asynchronously emit observability event to Inngest for live tracking
        asyncio.create_task(
            inngest_client.send(
                inngest.Event(
                    name="rag/query_pdf_ai",
                    data={
                        "question": req.question,
                        "owner_id": identity.id,
                        "top_k": req.top_k,
                        "model": req.model,
                    },
                )
            )
        )

        return ChatResponse(**result)

    except Exception as e:
        logger.error(f"Chat execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/history")
def get_chat_history(
    identity: IdentityContext = Depends(get_security_context),
    session_key: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Retrieves recent conversation history belonging strictly to the current caller."""
    query = db.query(ChatHistory).filter(ChatHistory.owner_id == identity.id)
    if session_key:
        query = query.filter(ChatHistory.session_key == session_key)
    records = query.order_by(ChatHistory.created_at.desc()).limit(limit).all()
    return [r.to_dict() for r in reversed(records)]


@app.delete("/api/chat/history")
def clear_chat_history(
    identity: IdentityContext = Depends(get_security_context),
    session_key: str | None = None,
    db: Session = Depends(get_db),
):
    """Clears conversation history for the current caller (optionally scoped to a session_key)."""
    query = db.query(ChatHistory).filter(ChatHistory.owner_id == identity.id)
    if session_key:
        query = query.filter(ChatHistory.session_key == session_key)
    deleted = query.delete()
    db.commit()
    return {"status": "success", "deleted_count": deleted}


# -----------------------------------------------------------------------------
# Sean Chen Semantic Memory & Admin Maintenance Endpoints (Phases 5 & 6)
# -----------------------------------------------------------------------------
@app.get("/api/user/profile")
def get_user_semantic_profile(
    identity: IdentityContext = Depends(require_authenticated),
    db: Session = Depends(get_db),
):
    """Retrieves the Sean Chen distilled semantic memory profile for the logged-in user."""
    prof = db.query(UserProfile).filter(UserProfile.owner_id == identity.id).first()
    if not prof:
        return {
            "owner_id": identity.id,
            "summary": None,
            "interests": [],
            "last_consolidated": None,
            "turn_count_at_last": 0,
        }
    return prof.to_dict()


@app.post("/api/user/consolidate-memory")
async def trigger_manual_memory_consolidation(
    identity: IdentityContext = Depends(require_authenticated),
    db: Session = Depends(get_db),
):
    """Manually triggers Sean Chen memory consolidation distillation for the current user."""
    total_turns = db.query(ChatHistory).filter(ChatHistory.owner_id == identity.id).count()
    if total_turns == 0:
        return {
            "status": "skipped",
            "message": "No conversation history exists yet to distill.",
            "turn_count": 0,
        }

    # Execute consolidation directly so user sees immediate results on UI
    result = await asyncio.to_thread(consolidate_user_memory, identity.id, total_turns)

    # Also emit Inngest telemetry event
    try:
        await inngest_client.send(
            inngest.Event(
                name="rag/consolidate_memory",
                data={
                    "owner_id": identity.id,
                    "turn_count": total_turns,
                },
            )
        )
    except Exception as e:
        logger.warning(f"Failed to emit inngest consolidate_memory event: {e}")

    return {
        "status": "success",
        "message": f"Memory consolidation completed for {identity.id} across {total_turns} turns.",
        "turn_count": total_turns,
        "profile": result,
    }


@app.post("/api/admin/purge-expired-guests")
def manual_purge_guests(
    max_age_hours: int = 2,
    identity: IdentityContext = Depends(require_admin),
):
    """Admin-only manual trigger for Phase 5 TTL reaper."""
    purged = purge_expired_guest_sessions(max_age_hours=max_age_hours)
    return {
        "status": "success",
        "purged_guest_sessions": purged,
        "max_age_hours": max_age_hours,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# -----------------------------------------------------------------------------
# Tenant-Scoped Document Upload & Management (Phase 2 Data Isolation)
# -----------------------------------------------------------------------------
@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    identity: IdentityContext = Depends(get_security_context),
):
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{file_ext}'. Supported formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    owner_dir = get_owner_storage_dir(identity.id)
    file_path = owner_dir / file.filename
    content = await file.read()
    file_path.write_bytes(content)

    try:
        # Ingest directly into Qdrant Cloud with strict owner_id tagging
        chunks_count = await asyncio.to_thread(
            process_and_ingest_document,
            str(file_path.resolve()),
            file.filename,
            identity.id,
        )

        # Emit background event to Inngest for dashboard tracking
        asyncio.create_task(
            inngest_client.send(
                inngest.Event(
                    name="rag/ingest_pdf",
                    data={
                        "doc_path": str(file_path.resolve()),
                        "pdf_path": str(file_path.resolve()),
                        "source_id": file.filename,
                        "owner_id": identity.id,
                    },
                )
            )
        )

        return {
            "status": "success",
            "filename": file.filename,
            "owner_id": identity.id,
            "chunks_count": chunks_count,
            "message": f"Successfully indexed {chunks_count} chunks into Qdrant Cloud.",
        }
    except Exception as e:
        logger.error(f"Ingestion failed for {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest document: {e}")


@app.get("/api/documents", response_model=list[DocumentInfo])
def list_documents(identity: IdentityContext = Depends(get_security_context)):
    """Lists only the documents belonging to the requesting user or guest session."""
    owner_dir = get_owner_storage_dir(identity.id)
    docs = []
    for f in owner_dir.iterdir():
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS:
            stat = f.stat()
            docs.append(DocumentInfo(filename=f.name, size_bytes=stat.st_size, modified_at=stat.st_mtime))
    return sorted(docs, key=lambda d: d.modified_at, reverse=True)


@app.delete("/api/documents/{filename}")
def delete_document(
    filename: str,
    identity: IdentityContext = Depends(get_security_context),
):
    """Deletes a document and its embeddings strictly within the caller's namespace."""
    owner_dir = get_owner_storage_dir(identity.id)
    file_path = owner_dir / filename
    if file_path.exists():
        file_path.unlink()

    # Delete vectors matching both source and owner_id
    QdrantStorage().delete_by_source(filename, owner_id=identity.id)
    logger.info(f"Deleted document {filename} and vector embeddings for owner {identity.id}.")
    return {"status": "success", "message": f"Successfully deleted {filename}"}


# Mount Inngest endpoint for production webhooks (/api/inngest)
inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf, rag_query_pdf_ai, rag_consolidate_memory, rag_ttl_reaper])
