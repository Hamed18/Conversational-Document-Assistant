import asyncio
import datetime
import json
import logging
import os
from pathlib import Path
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
from data_loader import embed_texts, load_and_chunk_pdf, load_and_chunk_pdf_with_metadata
from database import ChatHistory, GuestSession, User, get_db, init_db, SessionLocal
from vector_db import QdrantStorage

load_dotenv()

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


class FallbackAttempt(BaseModel):
    model: str
    model_name: str
    error: str | None = None
    latency_ms: float = 0.0


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    model_used: str
    latency_ms: float
    fallback_history: list[FallbackAttempt] = []
    num_contexts: int


class DocumentInfo(BaseModel):
    filename: str
    size_bytes: int
    modified_at: float


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
# Core RAG Ingestion Function (Tenant Partitioned)
# -----------------------------------------------------------------------------
def process_and_ingest_pdf(pdf_path: str, source_id: str | None = None, owner_id: str | None = None) -> int:
    source_id = source_id or Path(pdf_path).name
    owner_id = owner_id or "system"
    chunks_meta = load_and_chunk_pdf_with_metadata(pdf_path)
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


# -----------------------------------------------------------------------------
# Core Query & Multi-Tier Fallback Cascade Engine (Tenant Isolated & Memory-Aware)
# -----------------------------------------------------------------------------
def execute_query_cascade(
    question: str,
    owner_id: str,
    top_k: int = 5,
    requested_model: str | None = None,
    session_key: str | None = None,
) -> dict:
    store = QdrantStorage()
    query_vec = embed_texts([question])[0]

    # Search strictly filtered to this owner's vectors
    found = store.search(query_vec, owner_id=owner_id, top_k=top_k)

    # If the user/guest has uploaded no documents in their namespace:
    if not found["contexts"]:
        return {
            "answer": "You haven't uploaded any documents in this session yet. Please upload a PDF document first so I can analyze, summarize, or extract insights with citations for you.",
            "sources": [],
            "num_contexts": 0,
            "model_used": "system",
            "latency_ms": 2.0,
            "fallback_history": [],
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

    context_block = "\n\n".join(f"- {c}" for c in found["contexts"])
    system_prompt = (
        "You are AskFiles AI, a precise, intelligent, and grounded document assistant adhering to academic research standards.\n"
        "You have access to Episodic Memory of earlier turns in this conversation to maintain multi-turn context.\n"
        "MANDATORY CITATION RULES:\n"
        "1. After EVERY piece of information, claim, finding, or sentence you state from the document, you MUST append an inline numeric citation in brackets: [1], [2], [3], etc., citing the corresponding numbered context chunk (e.g. 'Support Vector Machines maximize the street width between opposite classes [1].').\n"
        "2. If multiple source chunks support a statement, combine them such as [1][2] or [1, 2].\n"
        "3. Use ONLY the numeric reference markers [1], [2], etc., corresponding to the numbered context chunks provided below. Do NOT write document filenames, page numbers, or raw URLs in the body text—they will be rendered automatically in the References layer at the bottom.\n"
        "4. Rely ONLY on the provided context chunks. If the context does not answer the question, state that clearly."
    )

    conversation_prefix = ""
    if history_block:
        conversation_prefix = f"Recent Conversation Context (Episodic Memory):\n{history_block}\n\n---\n\n"

    user_content = (
        f"{conversation_prefix}"
        f"Referenced Document Chunks:\n\n{context_block}\n\n"
        f"User Question: {question}\n\n"
        "Provide a grounded, comprehensive answer. Cite every fact or sentence using numeric citations in brackets like [1], [2] matching the source numbers above. If the question refers to earlier conversation context, respond seamlessly while keeping all factual claims cited."
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
        pdf_path = ctx.event.data["pdf_path"]
        source_id = ctx.event.data.get("source_id", pdf_path)
        chunks = load_and_chunk_pdf(pdf_path)
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
# FastAPI Application & REST Endpoints
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Conversational Document Assistant API",
    description="Production-grade RAG backend with multi-tenant data isolation, Inngest observability, and Neon PostgreSQL",
    version="2.1.0",
)

# Startup Hook
@app.on_event("startup")
def on_startup():
    bootstrap_default_admin()


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
        # 1. Execute grounded RAG query strictly partitioned to the caller's owner_id with Episodic Working Memory
        result = await asyncio.to_thread(
            execute_query_cascade,
            req.question,
            identity.id,
            req.top_k,
            req.model,
            req.session_key,
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

        # 3. Asynchronously emit observability event to Inngest for live tracking
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
# Tenant-Scoped Document Upload & Management (Phase 2 Data Isolation)
# -----------------------------------------------------------------------------
@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    identity: IdentityContext = Depends(get_security_context),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    owner_dir = get_owner_storage_dir(identity.id)
    file_path = owner_dir / file.filename
    content = await file.read()
    file_path.write_bytes(content)

    try:
        # Ingest directly into Qdrant Cloud with strict owner_id tagging
        chunks_count = await asyncio.to_thread(
            process_and_ingest_pdf,
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
    for f in owner_dir.glob("*.pdf"):
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
inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf, rag_query_pdf_ai])
