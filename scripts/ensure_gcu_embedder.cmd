@echo off
setlocal enabledelayedexpansion
:: ============================================================
:: Ensure the GCU embedding model is loaded in LM Studio (port 1234).
:: Without it, find_indicator / search_knowledge return HTTP 400 and the
:: assistant cannot route to indicators. LM Studio reloads only the CHAT model
:: on boot, NOT the embedder — this script closes that gap.
:: Idempotent: if the model is already loaded, `lms load` is a no-op.
:: No --ttl, so the model stays resident and never auto-unloads.
:: ============================================================
set LMS="%USERPROFILE%\.lmstudio\bin\lms.exe"
set MODEL=text-embedding-multilingual-e5-large-instruct
set LOG=C:\llm\gcu-export\scripts\ensure_gcu_embedder.log

echo [%date% %time%] start >> "%LOG%"

:: 1) Wait up to ~3 min for the LM Studio server to be up after boot.
set /a tries=0
:waitserver
%LMS% server status 2>nul | findstr /i "running" >nul
if %errorlevel%==0 goto serverup
set /a tries+=1
if !tries! geq 36 (
    echo [%date% %time%] server not up after 3min, aborting >> "%LOG%"
    exit /b 1
)
timeout /t 5 /nobreak >nul
goto waitserver

:serverup
echo [%date% %time%] server up, loading %MODEL% >> "%LOG%"

:: 2) Load the embedder (no-op if already loaded). -y for non-interactive.
%LMS% load %MODEL% -y >> "%LOG%" 2>&1
echo [%date% %time%] load exit=%errorlevel% >> "%LOG%"

:: 3) Verify the /v1/embeddings endpoint actually answers.
powershell -NoProfile -Command ^
  "try { $b = @{model='%MODEL%'; input=@('ping')} | ConvertTo-Json; $r = Invoke-RestMethod -Uri 'http://127.0.0.1:1234/v1/embeddings' -Method Post -Body $b -ContentType 'application/json' -TimeoutSec 30; if ($r.data[0].embedding.Count -gt 0) { exit 0 } else { exit 2 } } catch { exit 3 }"
echo [%date% %time%] verify exit=%errorlevel% >> "%LOG%"
exit /b 0
