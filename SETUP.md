# Quick Start & Local Setup Guide

Follow this step-by-step guide to clone, configure, and run **AskFiles (Conversational Document Assistant)** locally on your machine.

---

## 📋 System Prerequisites

Ensure you have the following installed before starting:
- **Python**: Version `3.11` or higher ([python.org](https://www.python.org/downloads/))
- **Node.js**: Version `18.x` or higher ([nodejs.org](https://nodejs.org/))
- **Git**: Installed and available in terminal
- *(Optional)* **Docker Desktop**: If running Qdrant locally in a container instead of Qdrant Cloud or the native binary.

---

## ⚡ Quick Start (One Command)

If you are on Windows, we provide automated launcher scripts:

### Using PowerShell:
```powershell
.\run_local.ps1
```

### Using Command Prompt (cmd) / Double-Click:
```cmd
run_local.bat
```

---

## 🛠️ Step-by-Step Manual Setup (After Clone or Fork)

### Step 1: Clone the Repository
```bash
git clone https://github.com/Hamed18/Conversational-Document-Assistant.git
cd Conversational-Document-Assistant
```

---

### Step 2: Configure Environment Variables

Create your local `.env` configuration file from the template:

```bash
# On Linux / macOS / Git Bash:
cp .env.example .env

# On Windows PowerShell:
Copy-Item .env.example .env
```

Open `.env` and fill in your keys:
```env
# OpenRouter API Configuration (For LLMs & Embeddings)
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Multi-Tier Reasoning Cascade
MODEL_PRIMARY=google/gemini-2.5-flash
MODEL_FALLBACK_1=qwen/qwen-2.5-72b-instruct
MODEL_FALLBACK_2=nvidia/nemotron-3-super-120b-a12b:free
MODEL_FALLBACK_CHAIN=google/gemini-2.5-flash,qwen/qwen-2.5-72b-instruct,nvidia/nemotron-3-super-120b-a12b:free

# Vector Database (Qdrant Cloud or Local)
# For Qdrant Cloud:
QDRANT_URL=https://your-cluster-id.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key_here
QDRANT_COLLECTION=docs

# For Local Qdrant (uncomment if running locally):
# QDRANT_URL=http://localhost:6333
# QDRANT_API_KEY=

# Inngest Configuration
INNGEST_EVENT_KEY=your_inngest_event_key
INNGEST_SIGNING_KEY=your_inngest_signing_key
```

---

### Step 3: Set Up Python Backend Virtual Environment

```bash
# 1. Create a Python virtual environment
python -m venv .venv

# 2. Activate the virtual environment
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On Windows CMD:
.\.venv\Scripts\activate.bat
# On Linux / macOS:
source .venv/bin/activate

# 3. Upgrade pip and install all backend dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

### Step 4: Set Up React Frontend Dependencies

Open a second terminal or navigate to the `frontend` directory:

```bash
cd frontend
npm install
cd ..
```

---

### Step 5: Start the Vector Database (Choose One Option)

#### Option A: Qdrant Cloud (Recommended - Zero Local Overhead)
If you provided a `QDRANT_URL` and `QDRANT_API_KEY` in `.env`, your cluster is already running in the cloud. **Skip to Step 6.**

#### Option B: Native Windows Binary (No Docker Required)
```powershell
.\qdrant_server\qdrant.exe
```
> *Runs on `http://localhost:6333`. Access the local web dashboard at `http://localhost:6333/dashboard`.*

#### Option C: Docker Compose
```bash
docker compose up -d
```

---

### Step 6: Start the FastAPI Backend Worker

In your backend terminal (with `.venv` activated):

```bash
# Run the FastAPI server with auto-reload enabled
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

- **Swagger API Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Probe Endpoint**: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- **Inngest Webhook**: [http://127.0.0.1:8000/api/inngest](http://127.0.0.1:8000/api/inngest)

---

### Step 7: Start the React Frontend Application

In your frontend terminal:

```bash
cd frontend
npm run dev
```

- **Live Local UI**: [http://localhost:3000](http://localhost:3000)
- The Vite dev server will start and automatically proxy `/api` requests to your FastAPI backend on `http://localhost:8000`.

---

### Step 8: (Optional) Start the Inngest Local Dev Server

To inspect execution DAGs, step latencies, retries, and events locally:

```bash
npx inngest-cli dev -u http://127.0.0.1:8000/api/inngest --no-discovery
```

- **Inngest Local Dashboard**: [http://localhost:8288](http://localhost:8288)

---

## 🧪 Verifying the Local Setup

Test the backend health via PowerShell:
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health
```
Expected output:
```json
{
  "status": "healthy",
  "service": "Conversational-Document-Assistant",
  "is_production": false,
  "qdrant_cloud": true,
  "inngest_cloud": true
}
```

Open [http://localhost:3000](http://localhost:3000) in your browser:
1. Upload a PDF document using the drag-and-drop zone.
2. Ask questions about the uploaded document.
3. Verify that responses include inline citation pills (`[Source: ..., Page: ..., Section: ...]`) and expandable source badges.
