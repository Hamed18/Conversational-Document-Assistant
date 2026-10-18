import asyncio
import datetime
import logging
import os
from pathlib import Path
import time
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import inngest
import inngest.fast_api
from openai import OpenAI
from pydantic import BaseModel, Field

from custom_types import RAGChunkAndSrc, RAGSearchResult, RAGUpsertResult
from data_loader import embed_texts, load_and_chunk_pdf, load_and_chunk_pdf_with_metadata
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

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------------------------
# Pydantic Schemas for REST API
# -----------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question about the ingested documents")
    top_k: int = Field(5, ge=1, le=20, description="Number of context chunks to retrieve")
    model: str | None = Field(None, description="Optional primary model override")


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
    """
    Returns prioritized list of (step_key, model_id, display_name).
    Prioritized by Latency & Quality:
    1. Gemini 2.5 Flash: ~1.8-3.5s latency, premier instruction following & context synthesis.
    2. Qwen 2.5 72B: ~2-3.2s latency, leading open-weights reasoning & factuality.
    3. Nemotron 120B: ~6s latency, high-capacity 120B dense model with free-tier safeguard.
    """
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
# Core RAG Ingestion Function
# -----------------------------------------------------------------------------
def process_and_ingest_pdf(pdf_path: str, source_id: str | None = None) -> int:
    source_id = source_id or Path(pdf_path).name
    chunks_meta = load_and_chunk_pdf_with_metadata(pdf_path)
    if not chunks_meta:
        return 0

    texts = [c["text"] for c in chunks_meta]
    vecs = embed_texts(texts)
    ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{i}")) for i in range(len(chunks_meta))]
    payloads = [
        {
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
# Core Query & Multi-Tier Fallback Cascade Engine
# -----------------------------------------------------------------------------
def execute_query_cascade(question: str, top_k: int = 5, requested_model: str | None = None) -> dict:
    query_vec = embed_texts([question])[0]
    store = QdrantStorage()
    found = store.search(query_vec, top_k)

    context_block = "\n\n".join(f"- {c}" for c in found["contexts"])
    system_prompt = (
        "You are AskFiles AI, a precise, intelligent, and grounded document assistant.\n"
        "MANDATORY CITATION REQUIREMENT:\n"
        "1. After EVERY piece of information, claim, finding, or sentence you state, you MUST append an inline citation in square brackets [ ... ] citing the exact source file, page number, and section.\n"
        "2. Format: [Source: <filename>, Page: <page_number>, Section: <section_title>]\n"
        "   If section is unavailable or same as page, format as: [Source: <filename>, Page: <page_number>]\n"
        "3. Place the bracketed citation immediately following the fact or sentence (e.g. 'Random Forests combine multiple decision trees to reduce variance [Source: Ensemble.pdf, Page: 14, Section: Bagging & Forests].')\n"
        "4. Rely ONLY on the provided context. If the context does not answer the question, state that clearly."
    )
    user_content = (
        f"Context with document, page, and section provenance:\n\n{context_block}\n\n"
        f"User Question: {question}\n\n"
        "Provide a grounded, comprehensive answer. Add an inline citation in square brackets [Source: <filename>, Page: <page>, Section: <section>] after every sentence or statement of fact."
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
        vecs = embed_texts(chunks)
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{i}")) for i in range(len(chunks))]
        payloads = [{"source": source_id, "text": chunks[i]} for i in range(len(chunks))]
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
    top_k = int(ctx.event.data.get("top_k", 5))
    requested_model = ctx.event.data.get("model")

    result = await ctx.step.run(
        "execute-rag-cascade",
        lambda: execute_query_cascade(question, top_k, requested_model),
    )
    return result


# -----------------------------------------------------------------------------
# FastAPI Application & REST Endpoints
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Conversational Document Assistant API",
    description="Production-grade RAG backend with Inngest observability and Qdrant Cloud vector search",
    version="2.0.0",
)

# CORS Middleware (Allows Vercel Frontend to communicate with Render Backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Conversational-Document-Assistant",
        "is_production": IS_PRODUCTION,
        "qdrant_cloud": True,
        "inngest_cloud": bool(INNGEST_SIGNING_KEY),
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


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    try:
        # 1. Execute grounded RAG query with distributed model fallback cascade
        result = execute_query_cascade(
            question=req.question,
            top_k=req.top_k,
            requested_model=req.model,
        )

        # 2. Asynchronously emit observability event to Inngest for live tracking
        asyncio.create_task(
            inngest_client.send(
                inngest.Event(
                    name="rag/query_pdf_ai",
                    data={
                        "question": req.question,
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


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file_path = UPLOADS_DIR / file.filename
    content = await file.read()
    file_path.write_bytes(content)

    try:
        # Ingest directly into Qdrant Cloud
        chunks_count = process_and_ingest_pdf(str(file_path.resolve()), source_id=file.filename)

        # Emit background event to Inngest for dashboard tracking
        asyncio.create_task(
            inngest_client.send(
                inngest.Event(
                    name="rag/ingest_pdf",
                    data={
                        "pdf_path": str(file_path.resolve()),
                        "source_id": file.filename,
                    },
                )
            )
        )

        return {
            "status": "success",
            "filename": file.filename,
            "chunks_count": chunks_count,
            "message": f"Successfully indexed {chunks_count} chunks into Qdrant Cloud.",
        }
    except Exception as e:
        logger.error(f"Ingestion failed for {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest document: {e}")


@app.get("/api/documents", response_model=list[DocumentInfo])
def list_documents():
    docs = []
    for f in UPLOADS_DIR.glob("*.pdf"):
        stat = f.stat()
        docs.append(DocumentInfo(filename=f.name, size_bytes=stat.st_size, modified_at=stat.st_mtime))
    return sorted(docs, key=lambda d: d.modified_at, reverse=True)


@app.delete("/api/documents/{filename}")
def delete_document(filename: str):
    file_path = UPLOADS_DIR / filename
    if file_path.exists():
        file_path.unlink()
    QdrantStorage().delete_by_source(filename)
    logger.info(f"Deleted document {filename} and removed associated vector embeddings.")
    return {"status": "success", "message": f"Successfully deleted {filename}"}


# Mount Inngest endpoint for production webhooks (/api/inngest)
inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf, rag_query_pdf_ai])