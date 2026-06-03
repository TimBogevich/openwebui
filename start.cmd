@echo off
:: Copy .env.example to .env and fill in POSTGRES_PASSWORD, REMOTE_API_KEY, WEBUI_SECRET_KEY
:: Then: docker compose up -d
::
:: Native Windows fallback (without Docker) — see launchers/ folder

set "LAUNCHER_DIR=%~dp0"

:: Prompt for required secrets if .env doesn't exist
if not exist "%LAUNCHER_DIR%.env" (
    echo ERROR: .env file not found.
    echo Copy .env.example to .env and fill in your secrets.
    exit /b 1
)

docker compose --env-file "%LAUNCHER_DIR%.env" up -d
