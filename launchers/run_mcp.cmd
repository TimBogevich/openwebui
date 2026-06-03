@echo off
set "GCU_DATABASE_URL=postgresql://postgres:%POSTGRES_PASSWORD%@127.0.0.1:5432/postgres"
cd /d C:\llm\gcu-fork
c:\llm\openwebui\.venv\Scripts\python.exe gcu\mcp_postgres_server.py
