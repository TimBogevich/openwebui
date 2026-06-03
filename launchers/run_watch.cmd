@echo off
set "PGHOST=127.0.0.1"
set "PGPORT=5432"
set "PGUSER=postgres"
set "PGPASSWORD=%POSTGRES_PASSWORD%"
set "PGDATABASE=postgres"
set "ONLY_GCU=1"
set "NO_MOVE=1"
cd /d C:\llm\gcu-fork
c:\llm\openwebui\.venv\Scripts\python.exe gcu\watch_uploads.py C:\llm\openwebui\data\uploads
