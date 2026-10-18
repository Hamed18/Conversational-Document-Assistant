# DevOps Implementation & Cloud Architecture Guide

This document provides a comprehensive technical guide to the DevOps practices, containerization, cloud deployment architecture, observability pipelines, and enterprise hyperscaler comparisons (AWS & Azure) implemented for **AskFiles (Conversational Document Assistant)**.

---

## 📌 Table of Contents
1. [Production Cloud Deployment Summary](#1-production-cloud-deployment-summary)
2. [Docker Containerization & CLI Command Reference](#2-docker-containerization--cli-command-reference)
3. [Step-by-Step DevOps Deployment Playbook](#3-step-by-step-devops-deployment-playbook)
   - [A. Backend Web Service on Render (Docker)](#a-backend-web-service-on-render-docker)
   - [B. Inngest Cloud Orchestration & Webhooks](#b-inngest-cloud-orchestration--webhooks)
   - [C. Frontend Edge Deployment on Vercel](#c-frontend-edge-deployment-on-vercel)
   - [D. Managed Vector Database on Qdrant Cloud](#d-managed-vector-database-on-qdrant-cloud)
4. [Dockerfile Architecture & DevOps Ecosystem Integration](#4-dockerfile-architecture--devops-ecosystem-integration)
5. [Observability, Tracing, and Failure Resilience in Production](#5-observability-tracing-and-failure-resilience-in-production)
6. [Free-Tier Cloud Ecosystem vs. Enterprise Hyperscalers (AWS & Azure)](#6-free-tier-cloud-ecosystem-vs-enterprise-hyperscalers-aws--azure)

---

## 1. Production Cloud Deployment Summary

The production architecture leverages a decoupled microservices design hosted entirely on **100% free-tier** modern cloud infrastructure:

```
┌─────────────────────────────────┐
│     AskFiles React Frontend     │  --> Deployed on Vercel (Edge CDN)
│   (Vite + Tailwind CSS + SPA)   │      URL: https://askfiles.vercel.app
└───────────────┬─────────────────┘
                │ HTTPS REST API
                ▼
┌─────────────────────────────────┐
│     FastAPI Backend Engine      │  --> Deployed on Render (Docker Container)
│    (Uvicorn + Dynamic $PORT)    │      URL: https://conversational-document-assistant.onrender.com
└───────┬───────────────┬─────────┘
        │               │
        ▼               ▼
┌──────────────┐ ┌──────────────┐
│ Qdrant Cloud │ │Inngest Cloud │  --> Managed Free Cloud Platforms
│ (AWS Region) │ │ (Event DAG & │      Qdrant: aws.cloud.qdrant.io:6333
│ 1GB Cluster  │ │ Observability│      Inngest: app.inngest.com
└──────────────┘ └──────────────┘
```

### Live Endpoints

| Component | Provider | Live Production URL |
| :--- | :--- | :--- |
| **Frontend Application** | Vercel Edge | [https://askfiles.vercel.app](https://askfiles.vercel.app/) |
| **Backend REST API** | Render Docker | [https://conversational-document-assistant.onrender.com](https://conversational-document-assistant.onrender.com) |
| **Backend Health Probe** | Render Docker | [https://conversational-document-assistant.onrender.com/api/health](https://conversational-document-assistant.onrender.com/api/health) |
| **Inngest Webhook Endpoint** | Render Docker | [https://conversational-document-assistant.onrender.com/api/inngest](https://conversational-document-assistant.onrender.com/api/inngest) |
| **Vector Database Cluster** | Qdrant Cloud | `https://c87eac77-a5d3-4754-bb7c-aa2e03abfc55.sa-east-1-0.aws.cloud.qdrant.io` |
| **Source Code Repository** | GitHub | [https://github.com/Hamed18/Conversational-Document-Assistant](https://github.com/Hamed18/Conversational-Document-Assistant.git) |

---

## 2. Docker Containerization & CLI Command Reference

Below are the exact commands used to build, test, run, and inspect the backend Docker container locally and for deployment:

### 🔨 Build the Container Image
```bash
# Build the production Docker image using the root Dockerfile
docker build -t askfiles-backend:latest .

# Build without using cached layers (clean build)
docker build --no-cache -t askfiles-backend:latest .
```

### 🚀 Run the Container Locally
```bash
# Run container with environment file and port mapping (8000 -> 8000)
docker run -d \
  --name askfiles-backend \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/uploads:/app/uploads \
  askfiles-backend:latest

# Run interactively with terminal output attached
docker run --rm -it \
  -p 8000:8000 \
  --env-file .env \
  askfiles-backend:latest
```

### 🔍 Inspect & Debug Running Containers
```bash
# View live streaming container logs
docker logs -f askfiles-backend

# Tail the last 100 log lines
docker logs --tail 100 askfiles-backend

# Open an interactive shell inside the container
docker exec -it askfiles-backend sh

# Inspect container health and resource utilization
docker stats askfiles-backend
docker inspect askfiles-backend
```

### 🛑 Stop & Cleanup Container
```bash
# Stop and remove the container
docker stop askfiles-backend
docker rm askfiles-backend

# Clean up dangling images
docker image prune -f
```

### 📦 Multi-Container Compose Commands (Local Development)
```bash
# Start all local microservices in background (Qdrant + App)
docker compose up -d

# Check status of compose services
docker compose ps

# View aggregate logs
docker compose logs -f

# Shut down all services and remove volumes
docker compose down -v
```

---

## 3. Step-by-Step DevOps Deployment Playbook

### A. Backend Web Service on Render (Docker)

1. **Service Creation**:
   - Navigate to [dashboard.render.com](https://dashboard.render.com/) ➜ **New +** ➜ **Web Service**.
   - Connect repository: `https://github.com/Hamed18/Conversational-Document-Assistant`.

2. **UI Settings & Build Configuration**:
   - **Name**: `conversational-document-assistant`
   - **Region**: Choose closest to target audience (e.g., Frankfurt / Ohio / Oregon).
   - **Runtime**: `Docker` *(Render auto-detects `Dockerfile`)*.
   - **Instance Type**: `Free` (0.1 CPU, 512 MB RAM).
   - **Health Check Path**: `/api/health`
   - **Auto-Deploy**: `On Commit` (triggers build upon pushing to `main`).
   - **Docker Build Context**: `.` *(Root directory)*.
   - **Dockerfile Path**: `./Dockerfile`.
   - **Docker Command**: *Leave blank* *(Dockerfile's dynamic `$PORT` CMD handles this)*.
   - **Pre-Deploy Command**: *Leave blank*.
   - **Build Filters (Ignored Paths)**:
     ```text
     frontend/**
     docs/**
     README.md
     ```
     *(Prevents unnecessary backend container rebuilds when updating frontend UI or documentation).*

3. **Environment Variables Added in Render**:

| Variable Key | Configuration Value | Description |
| :--- | :--- | :--- |
| `QDRANT_URL` | `https://c87eac77-a5d3-4754-bb7c-aa2e03abfc55.sa-east-1-0.aws.cloud.qdrant.io` | Remote Qdrant Cloud cluster endpoint |
| `QDRANT_API_KEY` | `eyJhbGciOiJIUzI1NiIsIn...` | Qdrant Cloud JWT authentication key |
| `QDRANT_COLLECTION` | `docs` | Target vector collection name |
| `OPENROUTER_API_KEY` | `sk-or-v1-b6faa6080...` | API key for distributed model inferencing & embeddings |
| `OPENROUTER_BASE_URL`| `https://openrouter.ai/api/v1` | OpenRouter endpoint |
| `OPENAI_API_KEY` | `sk-or-v1-b6faa6080...` | Compatibility key for OpenAI client libraries |
| `OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI compatibility base URL |
| `INNGEST_SIGNING_KEY`| `signkey-prod-62e4f46d...` *(or Inngest app key)* | HMAC-SHA256 signature key for Inngest webhook authentication |
| `INNGEST_EVENT_KEY` | `7jiAUMvZTZhMSJ7a...` | Inngest event emission authorization key |
| `MODEL_FALLBACK_CHAIN`| `google/gemini-2.5-flash,qwen/qwen-2.5-72b-instruct,nvidia/nemotron-3-super-120b-a12b:free` | Model cascade configuration |

---

### B. Inngest Cloud Orchestration & Webhooks

1. **Dashboard Navigation**:
   - Open [app.inngest.com](https://app.inngest.com/) ➜ Go to **Apps** tab.
2. **Syncing the Webhook**:
   - Click **Sync App** / **Add App**.
   - Copy the green **Signing Key** (`signkey...`) displayed in Inngest into Render's `INNGEST_SIGNING_KEY` environment variable.
   - In **App URL**, enter:
     ```text
     https://conversational-document-assistant.onrender.com/api/inngest
     ```
   - Click **Sync app**.
3. **Registered Handlers**:
   - Inngest securely contacts `/api/inngest` via `PUT`, validates the HMAC signature, and registers:
     - `RAG: Ingest PDF` (throttled background document ingestion).
     - `RAG: Query PDF AI` (asynchronous telemetry and query trace logging).

---

### C. Frontend Edge Deployment on Vercel

1. **Project Setup**:
   - Open [vercel.com](https://vercel.com/) ➜ Click **Add New...** ➜ **Project**.
   - Select repository: `Hamed18/Conversational-Document-Assistant`.
2. **Build & Directory Settings**:
   - **Project Name**: `AskFiles`
   - **Framework Preset**: `Vite` *(auto-detected)*.
   - **Root Directory**: `frontend` *(pointing to the React SPA folder)*.
   - **Build Command**: `npm run build` *(compiles via Vite into `frontend/dist`)*.
   - **Output Directory**: `dist`.
3. **Environment Variables**:
   - **Key**: `VITE_API_BASE_URL`
   - **Value**: `https://conversational-document-assistant.onrender.com`
4. **Single-Page Application (SPA) Routing**:
   - Configured via `frontend/vercel.json`:
     ```json
     {
       "rewrites": [
         {
           "source": "/(.*)",
           "destination": "/index.html"
         }
       ]
     }
     ```
     *(Ensures all deep links and client-side browser routes resolve cleanly to `index.html` without 404 errors).*

---

### D. Managed Vector Database on Qdrant Cloud

1. **Cluster Provisioning**:
   - Deployed on AWS South America (`sa-east-1`) Free Tier (1 GB RAM, 0.5 vCPU).
2. **Payload Indexing**:
   - Created a keyword index on `source` field:
     ```python
     client.create_payload_index(
         collection_name="docs",
         field_name="source",
         field_schema="keyword",
     )
     ```
     *(Required for fast metadata filtering and single-document deletions via `FilterSelector`).*
3. **Context Enrichment**:
   - Chunks stored with high-dimensional 3072 embeddings (`text-embedding-3-large`) alongside structured metadata:
     `{ "text": "...", "source": "filename.pdf", "page": 12, "section": "SVM Hyperplane" }`.

---

## 4. Dockerfile Architecture & DevOps Ecosystem Integration

### Deep Dive into the Multi-Stage `Dockerfile`

```dockerfile
# 1. Base Layer: Lightweight Debian-based Python image (slim)
FROM python:3.13-slim

WORKDIR /app

# 2. Optimization flags: Avoid writing .pyc byte-code & force real-time stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# 3. System dependencies: Install curl & CA certificates for SSL and health probes
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 4. Dependency caching: Copy only requirements.txt first to exploit Docker layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 5. Application Directories
RUN mkdir -p /app/uploads

# 6. Copy Application Source Code
COPY main.py data_loader.py vector_db.py custom_types.py ./

EXPOSE 8000

# 7. Dynamic Port Binding for Cloud Providers (Render, Cloud Run, Heroku)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

### Why This Design Fits the DevOps Ecosystem:

1. **Layer Caching Optimization**:
   - `COPY requirements.txt ./` is separated from `COPY . .`. If application code changes, Docker does not re-download or re-install Python dependencies, reducing build times from minutes to seconds.
2. **Minimal Attack Surface**:
   - `python:3.13-slim` eliminates compilers, build utilities, and unneeded packages, keeping the image size small (~220 MB) and minimizing CVE vulnerabilities.
3. **Cloud-Native Dynamic `$PORT` Binding**:
   - Cloud platforms (Render, AWS App Runner, Google Cloud Run) assign dynamic ports to containers via the `$PORT` environment variable. The command `sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"` dynamically resolves `$PORT` while defaulting to `8000` locally.
4. **Portability Across Runtimes**:
   - The same container runs identically on:
     - Local developer machines (`docker run`).
     - Render Web Services.
     - Kubernetes clusters (`Pod` / `Deployment`).
     - AWS ECS Fargate or Azure Container Apps.

---

## 5. Observability, Tracing, and Failure Resilience in Production

### The 3 Pillars of Observability in AskFiles

```
            OBSERVABILITY
           /      |      \
     METRICS    LOGS    TRACES
     (Latency) (Stdout) (Inngest DAG)
```

1. **Metrics**:
   - Measured per model attempt (`latency_ms`).
   - Telemetry emitted directly to the UI badge and Inngest execution history.
2. **Logs**:
   - Formatted Uvicorn access logs and structured error events emitted to `stdout`/`stderr` captured by Render Log Streams.
3. **Traces**:
   - Inngest workflows provide distributed execution graphs (DAGs) representing each processing step:
     `load` ➜ `chunk` ➜ `embed` ➜ `upsert` ➜ `query` ➜ `synthesize`.

### Why Observability is Critical When Systems Fail in Production

Modern AI applications depend on external non-deterministic third-party APIs (LLMs, embedding providers, remote vector databases). Traditional web applications fail with simple HTTP status codes; AI applications fail in nuanced ways:

- **Provider Rate Limiting (HTTP 429)**: An LLM provider may suddenly throttle requests during traffic spikes.
- **Context Window Exhaustion**: A query with large chunks may exceed an LLM's maximum context length.
- **Model Hallucination / Timeout**: An upstream model may hang for 30+ seconds before aborting.

#### How Our Architecture Solves This:
- **Resilient Distributed Fallback**:
  - If **Gemini 2.5 Flash** fails or returns a 429, the system automatically falls back to **Qwen 2.5 72B Instruct**, and subsequently to **NVIDIA Nemotron 120B**.
- **Auditability via Inngest Traces**:
  - DevOps engineers do not need to reproduce errors locally. Inngest captures the exact prompt payload, context chunks, and upstream provider stack trace.
- **Idempotency & Automatic Retries**:
  - Inngest steps run idempotently with exponential backoff, ensuring interrupted document processing resumes without duplicating vector embeddings in Qdrant.

---

## 6. Free-Tier Cloud Ecosystem vs. Enterprise Hyperscalers (AWS & Azure)

A core DevOps architectural decision was building AskFiles using modern, developer-first free-tier cloud platforms. Below is an architectural mapping comparing our setup with equivalent enterprise services on **Amazon Web Services (AWS)** and **Microsoft Azure**:

### Service Equivalence Matrix

| Architecture Layer | Our Free-Tier Stack | AWS Equivalent | Microsoft Azure Equivalent |
| :--- | :--- | :--- | :--- |
| **Frontend SPA Hosting** | **Vercel** (Global Edge CDN) | **AWS S3 + CloudFront** or **AWS Amplify** | **Azure Static Web Apps** or **Blob Storage + Azure CDN** |
| **Backend Container Service**| **Render** (Free Docker Web Service)| **AWS App Runner** or **AWS ECS Fargate** | **Azure Container Apps** or **Azure App Service (Linux)** |
| **Managed Vector Database** | **Qdrant Cloud** (Free 1GB Cluster) | **AWS OpenSearch Serverless (Vector Engine)** or **Amazon Bedrock Knowledge Bases** | **Azure AI Search** (formerly Cognitive Search with Vector Support) |
| **Workflow & Observability** | **Inngest Cloud** (Serverless Queues) | **AWS Step Functions + SQS + EventBridge** | **Azure Logic Apps + Service Bus + Event Grid** |
| **Model Serving / LLM Gateway** | **OpenRouter** (Multi-Model Cascade) | **Amazon Bedrock** (Claude, Titan, Llama) | **Azure OpenAI Service** (GPT-4o, Embeddings) |

---

### In-Depth Comparison: Can We Deploy This Identically to AWS or Azure?

#### 1. Backend Container Deployment
- **Can it be deployed identically?** **YES.**
- **AWS Deployment**: Push the same Docker image to **Amazon ECR** (Elastic Container Registry) and deploy to **AWS App Runner** or **ECS Fargate**. Both run containerized web services, support dynamic `$PORT` assignment, and offer built-in SSL and health checking.
- **Azure Deployment**: Push to **Azure Container Registry (ACR)** and deploy to **Azure Container Apps (ACA)**. ACA is built on Kubernetes (K8s) and KEDA, providing serverless scale-to-zero capability identical to Render's free tier behavior.
- **Key Difference**: AWS and Azure require configuring IAM roles, VPC subnets, Security Groups, and container registry authentication credentials, whereas Render requires zero VPC configuration.

#### 2. Frontend React SPA Deployment
- **Can it be deployed identically?** **YES.**
- **AWS Deployment**: Run `npm run build`, upload the `dist/` directory to an **Amazon S3** bucket configured for static web hosting, and attach an **Amazon CloudFront** distribution with custom error responses routing `404` to `/index.html` (identical to `vercel.json` rewrites). Alternatively, connect via **AWS Amplify Hosting**.
- **Azure Deployment**: Deploy to **Azure Static Web Apps (SWA)** via GitHub Actions. SWA automatically builds Vite React applications and manages global SSL and routing via `staticwebapp.config.json`.

#### 3. Vector Database
- **Can it be deployed identically?** **YES (with architectural trade-offs).**
- **AWS**: Use **Amazon OpenSearch Serverless** with Vector Search enabled or deploy Qdrant self-hosted on an EC2/EKS instance using the official Qdrant Helm chart.
- **Azure**: Use **Azure AI Search**, which indexes vector embeddings and supports hybrid search (vector cosine + BM25 keyword search), identical to Qdrant's payload filters.
- **Trade-off**: Managed hyperscaler vector services on AWS/Azure do not offer permanent free tiers and incur baseline hourly cluster charges (~$50–$200/month). Qdrant Cloud provides a permanent free 1GB cluster.

#### 4. Event Orchestration & Observability
- **Can it be deployed identically?** **YES (requires multiple decoupled services).**
- **Inngest vs. AWS/Azure**:
  - In our architecture, **Inngest Cloud** provides step-level tracing, retries, throttling, and a web dashboard out of the box in a single SDK (`inngest.fast_api.serve`).
  - To replicate Inngest on **AWS**, you must configure:
    1. **Amazon EventBridge** (to ingest events).
    2. **Amazon SQS** (for dead-letter queues and buffering).
    3. **AWS Step Functions** (state machine DAG for retries and steps).
    4. **AWS CloudWatch / X-Ray** (for traces and dashboards).
  - To replicate on **Azure**, you need **Event Grid + Service Bus + Logic Apps + Application Insights**.
- **DevOps Verdict**: Inngest reduces cloud infrastructure code by ~80% while delivering equivalent resilience and observability.

---

### Architectural Takeaway

| Dimension | Our Modern Cloud Architecture | Hyperscalers (AWS / Azure) |
| :--- | :--- | :--- |
| **Setup Time** | Under 15 minutes | Several hours / days (IAM, VPCs, DNS) |
| **Infrastructure as Code** | Minimal (`Dockerfile`, `vercel.json`) | Extensive (Terraform, CloudFormation, Bicep) |
| **Monthly Cost** | **$0.00 (100% Free Tiers)** | $80 – $300+ / month (minimum provisioned costs) |
| **Portability** | High (OCI Containers, Standard REST) | High (Standard containers, cloud-agnostic SDKs) |
| **Best Suited For** | Startups, POCs, Production MVPs, Portfolio | Large Enterprises requiring strict VPC peering & compliance |
