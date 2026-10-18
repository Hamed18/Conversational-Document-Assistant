# System Architecture & Data Flow Documentation

This document provides architectural blueprints and end-to-end data flow diagrams for the **Conversational Document Assistant** RAG application.

---

## 1. System Architecture Diagram

```mermaid
flowchart TB
    subgraph ClientLayer ["Client & Ingress Layer"]
        User["User (Browser / Mobile)"]
        CF_Chat["Cloudflare Tunnel: Chatbot\n(Public HTTPS Port 8501)"]
        CF_Obs["Cloudflare Tunnel: Observability\n(Public HTTPS Port 8288)"]
        Local_Direct["Direct Localhost Access\n(http://localhost:8501 & :8288)"]
    end

    subgraph PresentationLayer ["Presentation Layer (Port 8501)"]
        Streamlit["Streamlit Web Application (streamlit_app.py)"]
        ChatInput["Pinned Bottom Chat Bar (st.chat_input)"]
        ChatFeed["Message Feed & Citations (st.chat_message)"]
        Sidebar["Sidebar: Sessions & Settings"]
        ChatStore[("Local Session Store\n(chat_history.json)")]
        UploadStore[("Document Cache\n(uploads/*.pdf)")]
    end

    subgraph OrchestrationLayer ["Orchestration & Observability Layer (Port 8288)"]
        InngestServer["Inngest Dev Server & Event Broker"]
        EventBus["Inngest Event Bus\n(rag/ingest_pdf, rag/query_pdf_ai)"]
        ExecutionGraph["Step Execution & State Engine"]
        ObsDashboard["Inngest Web UI Dashboard\n(Real-Time DAG Step Tracing)"]
    end

    subgraph BackendLayer ["Backend Application Worker (Port 8000)"]
        FastAPI["FastAPI / Uvicorn Server (main.py)"]
        InngestSDK["Inngest Python SDK Serve Handler"]
        DocProcessor["Document Parser & Chunker\n(PyPDF + LlamaIndex SentenceSplitter)"]
        FallbackRouter["Distributed Model Fallback Router\n(Gemini ➜ Qwen ➜ Nemotron)"]
    end

    subgraph StorageLayer ["Vector Database & Storage (Port 6333)"]
        Qdrant["Native Qdrant Vector Engine (qdrant.exe)"]
        DocsCollection[("Collection: 'docs'\n(3072-dim Cosine Metric)")]
        QdrantStorage[("On-Disk Storage & WAL\n(./qdrant_server/storage)")]
    end

    subgraph ExternalServices ["External AI Provider (OpenRouter API)"]
        OpenRouter["OpenRouter Gateway (https://openrouter.ai/api/v1)"]
        EmbedModel["Embedding: text-embedding-3-large (3072 dim)"]
        LLM_Tier1["Tier 1: google/gemini-2.5-flash (~1.8s)"]
        LLM_Tier2["Tier 2: qwen/qwen-2.5-72b-instruct (~2.5s)"]
        LLM_Tier3["Tier 3: nvidia/nemotron-3-super-120b-a12b:free (~6.0s)"]
    end

    %% Client to Ingress
    User --> CF_Chat
    User --> CF_Obs
    User --> Local_Direct

    %% Ingress to Presentation & Observability
    CF_Chat --> Streamlit
    Local_Direct --> Streamlit
    CF_Obs --> InngestServer
    Local_Direct --> InngestServer

    %% Presentation Internal
    Streamlit --- ChatInput
    Streamlit --- ChatFeed
    Streamlit --- Sidebar
    Sidebar <--> ChatStore
    Sidebar --> UploadStore

    %% Presentation to Inngest & Backend
    Streamlit -->|Dispatch Events via Inngest SDK| EventBus
    Streamlit -->|Poll Run Status & Output /v1/runs| InngestServer
    InngestServer <--> ObsDashboard

    %% Inngest Orchestration to Backend
    EventBus --> ExecutionGraph
    ExecutionGraph <-->|Execute Steps /api/inngest| FastAPI
    FastAPI --- InngestSDK
    InngestSDK --> DocProcessor
    InngestSDK --> FallbackRouter

    %% Backend to Storage & External
    DocProcessor --> UploadStore
    DocProcessor -->|Embed Chunks| OpenRouter
    FallbackRouter -->|Generate Embeddings & Answers| OpenRouter
    OpenRouter --- EmbedModel
    OpenRouter --- LLM_Tier1
    OpenRouter --- LLM_Tier2
    OpenRouter --- LLM_Tier3

    FastAPI <-->|Vector Upsert & Semantic Search| Qdrant
    Qdrant --- DocsCollection
    DocsCollection --- QdrantStorage
```

---

## 2. End-to-End Data Flow Diagram (DFD)

The system manages two distinct asynchronous data pipelines:
1. **Document Ingestion Pipeline** (PDF Parsing, Chunking, Embedding, and Indexing)
2. **Query & Distributed RAG Pipeline** (Semantic Search, Context Assembly, Multi-Tier LLM Cascading, and Result Telemetry)

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Browser
    participant UI as Streamlit UI (:8501)
    participant Inngest as Inngest Dev Server (:8288)
    participant Worker as FastAPI Worker (:8000)
    participant Qdrant as Qdrant Vector DB (:6333)
    participant OpenRouter as OpenRouter AI API

    %% =========================================================================
    %% PIPELINE 1: INGESTION
    %% =========================================================================
    rect rgb(235, 245, 255)
        note over User, OpenRouter: PIPELINE 1: Document Ingestion Flow (rag/ingest_pdf)
        User->>UI: Upload PDF Document via Sidebar
        UI->>UI: Save to uploads/{filename}.pdf
        UI->>Inngest: Send Event: "rag/ingest_pdf" {pdf_path, source_id}
        Inngest-->>UI: Event Accepted (event_id returned)
        Inngest->>Worker: Trigger "RAG: Ingest PDF" (throttled & rate-limited)

        rect rgb(250, 250, 250)
            note over Worker: Step 1: "load-and-chunk"
            Worker->>Worker: Parse PDF text (PyPDF)
            Worker->>Worker: Semantic chunking (LlamaIndex SentenceSplitter, 1000 size, 200 overlap)
        end

        rect rgb(250, 250, 250)
            note over Worker, OpenRouter: Step 2: "embed-and-upsert"
            Worker->>OpenRouter: POST /v1/embeddings (texts=chunks, model="text-embedding-3-large")
            OpenRouter-->>Worker: Return 3072-dimensional embedding vectors
            Worker->>Worker: Generate deterministic PointStructs (UUIDv5, vector, metadata)
            Worker->>Qdrant: Upsert vectors & payloads into collection "docs"
            Qdrant-->>Worker: Upsert confirmed (points indexed)
        end

        Worker-->>Inngest: Step complete: {ingested: count}
        Inngest->>Inngest: Record workflow Completed in observability log
    end

    %% =========================================================================
    %% PIPELINE 2: QUERY & DISTRIBUTED RAG
    %% =========================================================================
    rect rgb(240, 255, 240)
        note over User, OpenRouter: PIPELINE 2: Query & Distributed RAG Flow (rag/query_pdf_ai)
        User->>UI: Types Question in Bottom Pinned Input (st.chat_input)
        UI->>UI: Append user message to active session in chat_history.json
        UI->>Inngest: Send Event: "rag/query_pdf_ai" {question, top_k, model}
        Inngest-->>UI: Event Accepted (event_id)
        Inngest->>Worker: Trigger "RAG: Query PDF"

        rect rgb(250, 250, 250)
            note over Worker, Qdrant: Step: "embed-and-search"
            Worker->>OpenRouter: POST /v1/embeddings (text=[question])
            OpenRouter-->>Worker: Return query vector (3072 dim)
            Worker->>Qdrant: Search collection "docs" (query_vector, limit=top_k, distance=Cosine)
            Qdrant-->>Worker: Return top matching context chunks & source metadata
        end

        rect rgb(255, 245, 240)
            note over Worker, OpenRouter: Step: Distributed Model Fallback Cascade
            Worker->>Worker: Build Grounded Context Prompt

            alt Tier 1 Primary: Google Gemini 2.5 Flash
                Worker->>OpenRouter: POST /v1/chat/completions (model="google/gemini-2.5-flash")
                OpenRouter-->>Worker: Success (Answer returned in ~1.8s)
            else Tier 1 Fails (Rate Limit 429 / Timeout / Error)
                Inngest->>Inngest: Log Tier 1 Error Telemetry
                Worker->>OpenRouter: POST /v1/chat/completions (model="qwen/qwen-2.5-72b-instruct")
                OpenRouter-->>Worker: Success (Answer returned in ~2.5s)
            else Tier 2 Fails (Provider Outage)
                Inngest->>Inngest: Log Tier 2 Error Telemetry
                Worker->>OpenRouter: POST /v1/chat/completions (model="nvidia/nemotron-3-super-120b-a12b:free")
                OpenRouter-->>Worker: Success (Answer returned in ~6.0s)
            end
        end

        Worker-->>Inngest: Return {answer, sources, model_used, latency_ms, fallback_history}
        Inngest->>Inngest: Finalize DAG Run as Completed

        loop Poll for Run Output
            UI->>Inngest: GET /v1/events/{event_id}/runs
            Inngest-->>UI: Status: Completed, run_id
            UI->>Inngest: GET /v1/runs/{run_id}
            Inngest-->>UI: Full Output Payload
        end

        UI->>UI: Append Assistant reply & citations to chat_history.json
        UI-->>User: Render Answer Bubble, Latency Badge & Expandable Citations
    end
```

---

## 3. Data Transformations & Schemas

### A. Document Chunk & Embedding Schema
- **Chunk Size:** 1,000 characters with 200 characters semantic boundary overlap.
- **Embedding Vector:** 3,072-dimensional floating point dense vector (`text-embedding-3-large`).
- **Qdrant Point Payload:**
```json
{
  "id": "e6f47f20-96bc-5a4a-9eb6-0eb03a58e597",
  "vector": [0.0124, -0.0432, 0.0891, "...(3072 floats)"],
  "payload": {
    "source": "financial_report.pdf",
    "text": "In Q3 2026, total operating revenue reached $4.2B with a year-over-year increase of 14%..."
  }
}
```

### B. Inngest Event Schemas
- **Event: `rag/ingest_pdf`**
  ```json
  {
    "name": "rag/ingest_pdf",
    "data": {
      "pdf_path": "E:\\AI App\\Document Reader Application\\RAG App\\uploads\\contract.pdf",
      "source_id": "contract.pdf"
    }
  }
  ```
- **Event: `rag/query_pdf_ai`**
  ```json
  {
    "name": "rag/query_pdf_ai",
    "data": {
      "question": "What were the total revenues in Q3?",
      "top_k": 5,
      "model": "auto"
    }
  }
  ```

### C. Persistent Chat Session Schema (`chat_history.json`)
```json
{
  "active_session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "sessions": {
    "a1b2c3d4-e5f6-7890-abcd-ef1234567890": {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "What were the total revenues in Q3?",
      "created_at": 1729267000.12,
      "messages": [
        {
          "role": "user",
          "content": "What were the total revenues in Q3?",
          "timestamp": 1729267001.0
        },
        {
          "role": "assistant",
          "content": "Total operating revenue in Q3 reached $4.2B, representing a 14% YoY growth.",
          "model_used": "google/gemini-2.5-flash",
          "latency_ms": 1807.76,
          "sources": ["financial_report.pdf"],
          "fallback_history": [],
          "timestamp": 1729267003.8
        }
      ]
    }
  }
}
```
