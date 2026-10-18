# Local Deployment & Commands Guide

This guide provides step-by-step instructions for running the **PDF RAG Application** and the **Inngest Observability Dashboard** locally on your machine.

---

## 🏗️ Architecture & Local Port Map

| Component | Port | Local URL | Command / Service |
| :--- | :--- | :--- | :--- |
| **Streamlit Chatbot** | `8501` | [http://localhost:8501](http://localhost:8501) | `streamlit run streamlit_app.py` |
| **Inngest Observability** | `8288` | [http://localhost:8288](http://localhost:8288) | `npx inngest-cli dev -u http://127.0.0.1:8000/api/inngest` |
| **FastAPI Backend Worker** | `8000` | [http://localhost:8000/docs](http://localhost:8000/docs) | `uvicorn main:app --reload --port 8000` |
| **Qdrant Vector Database** | `6333` | [http://localhost:6333/dashboard](http://localhost:6333/dashboard) | `.\qdrant_server\qdrant.exe` *(or Docker)* |

---

## ⚡ Quick Start (One Command)

We have provided convenient automation scripts to start all 4 local services at once:

### Using PowerShell:
```powershell
.\run_local.ps1
```

### Using Windows Command Prompt / Double-Click:
```cmd
run_local.bat
```

---

## 📋 Manual Step-by-Step Commands

If you prefer running each service in its own terminal window, open 4 separate PowerShell terminals in the project root (`E:\AI App\Document Reader Application\RAG App`):

### Terminal 1: Start Qdrant Vector Database
You can choose either the **Native Windows binary (No Docker needed, Recommended)** or Docker Desktop:

**Option A (Native Windows Binary - Recommended):**
```powershell
.\qdrant_server\qdrant.exe
```
> *Zero overhead, no admin rights required, runs natively on port 6333.*

**Option B (Docker Desktop):**
```powershell
docker compose up -d
```

Verify Qdrant is running:
```powershell
curl.exe http://127.0.0.1:6333
```

---

### Terminal 2: Start FastAPI Backend Worker
Activates the virtual environment and starts the FastAPI service serving Inngest functions:
```powershell
.\.venv\Scripts\uvicorn.exe main:app --reload --port 8000
```
> *Exposes the Inngest function endpoints at `http://127.0.0.1:8000/api/inngest`.*

---

### Terminal 3: Start Inngest Observability Dev Server
Connects to the FastAPI backend to provide real-time step visualization, retries, and metrics:
```powershell
npx inngest-cli dev -u http://127.0.0.1:8000/api/inngest --no-discovery
```
> *Open **[http://localhost:8288](http://localhost:8288)** to monitor workflows, view step trees, and inspect model fallback triggers.*

---

### Terminal 4: Start Streamlit Frontend Chatbot
Launches the interactive user interface:
```powershell
.\.venv\Scripts\streamlit.exe run streamlit_app.py --server.port 8501
```
> *Open **[http://localhost:8501](http://localhost:8501)** in your browser to upload documents and query your knowledge base.*

---

## 🌐 (Optional) Exposing Public URLs via Cloudflare Quick Tunnels

If you need to share the application or access it from mobile devices or external networks without port forwarding, run:

### Expose Chatbot Interface (Port 8501):
```powershell
.\cloudflared.exe tunnel --url http://127.0.0.1:8501 --no-autoupdate
```

### Expose Inngest Observability Dashboard (Port 8288):
```powershell
.\cloudflared.exe tunnel --url http://127.0.0.1:8288 --no-autoupdate
```
> *Cloudflare will print an ephemeral HTTPS URL (e.g. `https://*.trycloudflare.com`) in the console. No account or API key required.*

---

## 🧠 Distributed Model Fallback Architecture

The system uses a 3-tier cascade prioritized by latency and reasoning quality:

1. **Tier 1 (Primary): `google/gemini-2.5-flash`**  
   - Ultra-low latency (~1.8s - 3.8s)  
   - Highest context fidelity & instruction synthesis
2. **Tier 2 (Fallback 1): `qwen/qwen-2.5-72b-instruct`**  
   - Fast reasoning (~2.5s - 4.5s)  
   - SOTA open-weights logic and factual extraction
3. **Tier 3 (Fallback 2): `nvidia/nemotron-3-super-120b-a12b:free`**  
   - 120B parameter dense model (~5.5s - 6.5s)  
   - Free-tier safety net guaranteeing service continuity

Configure or modify the cascade in `.env`:
```env
MODEL_FALLBACK_CHAIN=google/gemini-2.5-flash,qwen/qwen-2.5-72b-instruct,nvidia/nemotron-3-super-120b-a12b:free
```
