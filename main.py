import logging
from fastapi import FastAPI
import inngest
import inngest.fast_api
from openai import OpenAI
from dotenv import load_dotenv
import uuid
import os
import datetime
from data_loader import load_and_chunk_pdf, embed_texts
from vector_db import QdrantStorage
from custom_types import RAQQueryResult, RAGSearchResult, RAGUpsertResult, RAGChunkAndSrc

load_dotenv()

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=False,
    serializer=inngest.PydanticSerializer()
)

@inngest_client.create_function(
    fn_id="RAG: Ingest PDF",
    trigger=inngest.TriggerEvent(event="rag/ingest_pdf"),
    throttle=inngest.Throttle(
        limit=2, period=datetime.timedelta(minutes=1)
    ),
    rate_limit=inngest.RateLimit(
        limit=1,
        period=datetime.timedelta(hours=4),
        key="event.data.source_id",
    ),
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


def get_fallback_models(requested_model: str | None = None) -> list[tuple[str, str, str]]:
    """
    Returns prioritized list of (step_key, model_id, display_name).
    Prioritized by Latency & Quality:
    1. Gemini 2.5 Flash: ~3.5-4.5s latency, premier instruction following & context synthesis.
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

    if requested_model:
        chain = [c for c in chain if c[1] == requested_model] + [c for c in chain if c[1] != requested_model]
        if not any(c[1] == requested_model for c in chain):
            step_key = requested_model.replace("/", "-").replace(":", "-").replace(".", "-")[:20]
            chain.insert(0, (step_key, requested_model, requested_model))
    return chain


@inngest_client.create_function(
    fn_id="RAG: Query PDF",
    trigger=inngest.TriggerEvent(event="rag/query_pdf_ai")
)
async def rag_query_pdf_ai(ctx: inngest.Context):
    def _search(question: str, top_k: int = 5) -> RAGSearchResult:
        query_vec = embed_texts([question])[0]
        store = QdrantStorage()
        found = store.search(query_vec, top_k)
        return RAGSearchResult(contexts=found["contexts"], sources=found["sources"])

    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))
    requested_model = ctx.event.data.get("model")

    found = await ctx.step.run("embed-and-search", lambda: _search(question, top_k), output_type=RAGSearchResult)

    context_block = "\n\n".join(f"- {c}" for c in found.contexts)
    user_content = (
        "Use the following context to answer the question.\n\n"
        f"Context:\n{context_block}\n\n"
        f"Question: {question}\n"
        "Answer concisely using the context above."
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
    latency_ms = 0
    fallback_history = []

    for step_key, model_id, display_name in models_to_try:
        def _invoke_model(m=model_id, name=display_name):
            import time
            t0 = time.time()
            try:
                res = client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": "You answer questions using only the provided context."},
                        {"role": "user", "content": user_content}
                    ],
                    max_tokens=1024,
                    temperature=0.2,
                )
                dt = (time.time() - t0) * 1000
                msg = res.choices[0].message
                text = (msg.content or getattr(msg, "reasoning", "") or "").strip()
                if not text:
                    raise ValueError(f"Model {m} returned empty response")
                return {
                    "success": True,
                    "answer": text,
                    "model": m,
                    "model_name": name,
                    "latency_ms": round(dt, 2),
                    "error": None
                }
            except Exception as e:
                dt = (time.time() - t0) * 1000
                logging.getLogger("uvicorn").warning(f"Distributed fallback: Model {m} failed in {dt:.0f}ms: {e}")
                return {
                    "success": False,
                    "answer": "",
                    "model": m,
                    "model_name": name,
                    "latency_ms": round(dt, 2),
                    "error": str(e)
                }

        step_res = await ctx.step.run(f"llm-{step_key}", _invoke_model)
        if step_res.get("success") and step_res.get("answer"):
            answer = step_res["answer"]
            model_used = step_res.get("model", model_id)
            latency_ms = step_res.get("latency_ms", 0)
            break
        else:
            fallback_history.append({
                "model": step_res.get("model", model_id),
                "model_name": step_res.get("model_name", display_name),
                "error": step_res.get("error", "Unknown error"),
                "latency_ms": step_res.get("latency_ms", 0)
            })

    if not answer:
        raise RuntimeError(f"All distributed LLM fallback models failed: {fallback_history}")

    return {
        "answer": answer,
        "sources": found.sources,
        "num_contexts": len(found.contexts),
        "model_used": model_used,
        "latency_ms": latency_ms,
        "fallback_history": fallback_history
    }

app = FastAPI()

inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf, rag_query_pdf_ai])