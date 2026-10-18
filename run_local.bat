@echo off
title PDF RAG Application Launcher
echo ==========================================================
echo    Starting PDF RAG Application ^& Observability Stack
echo ==========================================================

cd /d "%~dp0"

echo [1/4] Starting Qdrant Vector DB on port 6333...
start "Qdrant Vector DB" /min .\qdrant_server\qdrant.exe

echo [2/4] Starting FastAPI Backend on port 8000...
start "FastAPI Backend" /min .\.venv\Scripts\uvicorn.exe main:app --reload --port 8000

timeout /t 2 /nobreak >nul

echo [3/4] Starting Inngest Dev Server on port 8288...
start "Inngest Dev Server" /min npx inngest-cli dev -u http://127.0.0.1:8000/api/inngest --no-discovery

timeout /t 2 /nobreak >nul

echo [4/4] Starting Streamlit Chatbot on port 8501...
start "Streamlit Chatbot" .\.venv\Scripts\streamlit.exe run streamlit_app.py --server.port 8501

echo.
echo All services launched!
echo Chatbot: http://localhost:8501
echo Observability Dashboard: http://localhost:8288
echo.
pause
