# PowerShell 1-Click Runner for PDF RAG & Inngest Observability Stack
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Starting PDF RAG Application & Observability Stack     " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Start Qdrant Vector DB
Write-Host "[1/4] Starting Qdrant Vector DB on port 6333..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir'; .\qdrant_server\qdrant.exe" -WindowStyle Minimized

# 2. Start FastAPI Backend Worker
Write-Host "[2/4] Starting FastAPI Backend on port 8000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir'; .\.venv\Scripts\uvicorn.exe main:app --reload --port 8000" -WindowStyle Minimized

Start-Sleep -Seconds 2

# 3. Start Inngest Dev Server
Write-Host "[3/4] Starting Inngest Dev Server on port 8288..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir'; npx inngest-cli dev -u http://127.0.0.1:8000/api/inngest --no-discovery" -WindowStyle Minimized

Start-Sleep -Seconds 2

# 4. Start Streamlit Chatbot
Write-Host "[4/4] Starting Streamlit Chatbot on port 8501..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir'; .\.venv\Scripts\streamlit.exe run streamlit_app.py --server.port 8501"

Write-Host "`nAll services successfully launched!" -ForegroundColor Yellow
Write-Host "Chatbot URL:               http://localhost:8501" -ForegroundColor Cyan
Write-Host "Inngest Observability URL: http://localhost:8288" -ForegroundColor Cyan
Write-Host "FastAPI Documentation URL: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "Qdrant Dashboard URL:      http://localhost:6333/dashboard" -ForegroundColor Cyan
