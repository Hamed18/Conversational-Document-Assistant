# Production-Ready RAG AI Document Reader Application

A resilient, production-grade Retrieval-Augmented Generation (RAG) system built in Python for ingesting PDF documents and performing grounded Q&A with source citations. 

The application incorporates durability, observability, retries, and rate limiting using Inngest, Qdrant in Docker, LlamaIndex, OpenRouter (free-tier LLM & embeddings), FastAPI, and Streamlit.

---

## Architecture Overview

- **Frontend:** Streamlit (`streamlit_app.py`) for PDF uploads, interactive chat, and citation display.
- **Workflow & Orchestration:** Inngest (`inngest`) with FastAPI (`main.py`) providing step-level tracing, retries, concurrency throttling, and rate limiting per document.
- **Document Chunking:** LlamaIndex `SentenceSplitter` (`data_loader.py`) for semantic chunking with overlap.
- **Vector Database:** Qdrant running in Docker (`docker-compose.yml`) storing 3,072-dimensional embeddings with Cosine similarity.
- **Embeddings & LLM:** OpenRouter API (`text-embedding-3-large` embeddings + free-tier LLM models like `nvidia/nemotron-3-super-120b-a12b:free` or `openrouter/free`).

---

## Prerequisites

Before running the application, make sure you have:

1. **Python 3.13+** (or [uv](https://github.com/astral-sh/uv))
2. **Docker Desktop** installed and running
3. **Node.js & npx** installed (for the Inngest local dev server)
4. An **OpenRouter API Key**

---

## Setup & Installation

### 1. Environment Configuration

Ensure a `.env` file exists in the project root with the following settings:

```env
# OpenRouter API Configuration
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
# Recommended free models: nvidia/nemotron-3-super-120b-a12b:free, openrouter/free, liquid/lfm-2.5-2.6b:free
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free

# Compatible OpenAI settings (mapped to OpenRouter)
OPENAI_API_KEY=your_openrouter_api_key_here
OPENAI_BASE_URL=https://openrouter.ai/api/v1

# Qdrant Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=docs

# Inngest Dev Server Configuration
INNGEST_API_BASE=http://127.0.0.1:8288/v1
```

### 2. Install Python Dependencies

Using `uv` (recommended):
```powershell
python -m uv sync
```

Or using standard `pip`:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r pyproject.toml
```

---

## How to Run the Application

Running the application requires four services (Qdrant container + 3 terminal processes).

### Step 1: Start Qdrant Vector Database (Docker)

Start the Qdrant container with persistent volume storage:
```powershell
docker compose up -d
```
> Verify it is running by checking [http://localhost:6333/dashboard](http://localhost:6333/dashboard) or running `docker ps`.

---

### Step 2: Start the FastAPI Backend (Inngest Worker)

Open **Terminal 1** and start the FastAPI service:
```powershell
.\.venv\Scripts\uvicorn main:app --reload --port 8000
```
> This exposes the Inngest function endpoints at `http://127.0.0.1:8000/api/inngest`.

---

### Step 3: Start the Inngest Dev Server

Open **Terminal 2** and launch the Inngest local dev server to monitor and execute background steps:
```powershell
npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest
```
> Open [http://localhost:8288](http://localhost:8288) in your browser to inspect real-time runs, retries, and function logs.

---

### Step 4: Start the Streamlit Frontend

Open **Terminal 3** and run the Streamlit app:
```powershell
.\.venv\Scripts\streamlit run streamlit_app.py
```
> Streamlit will automatically open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Using the Application

1. **Ingest a Document:**
   - In the Streamlit web interface, drag and drop a PDF file into the uploader.
   - The app fires an Inngest background event (`rag/ingest_pdf`), chunks the text, embeds it via OpenRouter, and indexes the vectors into Qdrant.
   - Check the Inngest dev server dashboard at [http://localhost:8288](http://localhost:8288) to watch the steps execute.
2. **Query the Document:**
   - Type your question in the text box under "Ask a question about your PDFs".
   - Select how many top chunks to retrieve (default: `5`).
   - Click **Ask**. The system retrieves the most relevant context chunks from Qdrant, prompts the OpenRouter free LLM, and displays the answer along with source document citations.

---

## Troubleshooting

- **Qdrant Connection Refused:**
  Ensure Docker Desktop is running and run `docker compose up -d`.
- **Inngest Function Not Found / Polling Timeout:**
  Make sure both `uvicorn main:app --port 8000` and `npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest` are running before querying in Streamlit.
- **Model Rate Limits (429):**
  If the configured free model experiences upstream traffic, switch `OPENROUTER_MODEL` in `.env` to `openrouter/free` (which auto-routes to available free models) or another free model option and restart the FastAPI server.
"# RAG-App" 
