@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "DATA_DIR=c:\llm\openwebui\data"
set "WEBUI_SECRET_KEY=%WEBUI_SECRET_KEY%"
set "WEBUI_NAME=ГЦУ Ассистент"
set "DEFAULT_LOCALE=ru-RU"
set "DEFAULT_MODELS=qwen/qwen3.6-27b"
cd /d c:\llm\openwebui
c:\llm\openwebui\.venv\Scripts\open-webui.exe serve --host 0.0.0.0 --port 3000
