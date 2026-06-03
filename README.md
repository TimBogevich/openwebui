# ГЦУ Ассистент — RZD AI Assistant for Open WebUI

AI assistant for **RZD (Russian Railways) ГЦУ daily operational reports**. The AI answers questions about indicators, deviations, and red/yellow/green zones by querying a live PostgreSQL database.

---

## What's in this repo

| Path | Purpose |
|---|---|
| `docker-compose.yml` | Full stack: Postgres + MCP server + upload watcher + Open WebUI |
| `static/` | RZD branding (CSS theme, JS loader, RZD logo) |
| `gcu/` | Python tools: MCP server, Excel parser, filter, upload watcher |
| `launchers/` | Native Windows .cmd scripts (alternative to Docker) |
| `openwebui_config.json` | Model presets + filter code + tool server registration to re-apply via API |
| `.env.example` | Config template — copy to `.env` and fill in secrets |

---

## Quick Start (Docker)

### Requirements
- Docker + Docker Compose (WSL2 required on Windows)
- LM Studio running on the host at port 1234 (optional — for local 9B model)
- Remote API key for agentplatform.ru (or any OpenAI-compatible endpoint)

### Steps

```bash
# 1. Clone
git clone https://github.com/TimBogevich/openwebui.git
cd openwebui

# 2. Configure
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, REMOTE_API_KEY, WEBUI_SECRET_KEY

# 3. Start
docker compose up -d

# 4. Open
# http://localhost:3000
```

### Load report data

Drop ГЦУ Excel files into the watched uploads folder, **or** run the parser manually:

```bash
docker exec gcu-postgres psql -U postgres -c "SELECT count(*) FROM gtsu_search;"

# Parse a report manually:
docker run --rm -v $(pwd)/gcu:/app -v /path/to/excel:/data \
  -e PGHOST=gcu-postgres ... python /app/parse_gtsu_excel.py /data/ГЦУ-03-31.xlsx
```

---

## Architecture

```
User
  └─ Open WebUI :3000
       ├─ GCU Remote (Qwen 27B) → agentplatform.ru → MCP tool → PostgreSQL
       │    [native tool calling — model writes its own SQL, visible chip in UI]
       └─ ГЦУ 9B (локальный) → LM Studio :1234
            [filter injection — filter runs hardcoded SQL, injects result as context]
```

**Two DB access paths:**
- **Remote 27B** — model calls `gcu-postgres_query` MCP tool, writes its own SQL, result shown with citation chip
- **Local 9B** — `gcu_report_filter` (Open WebUI filter) auto-injects DB data for keyword questions (red zone, yellow zone, by-department). Real PostgreSQL data, no tool chip.

---

## Database schema

```sql
-- Main table: gtsu_search
-- 21 912 rows (31 days of March 2022 loaded from real ГЦУ Excel reports)
SELECT report_date, indicator, responsible,
       color_marker,           -- 2=red, 1=yellow, 0=green
       metrics->>'сутки_к_плану' AS dev_plan,  -- deviation as fraction: -0.097 = -9.7%
       text_comment
FROM gtsu_search
WHERE report_date = (SELECT max(report_date) FROM gtsu_search)
  AND color_marker = 2
ORDER BY (metrics->>'сутки_к_плану')::numeric ASC
LIMIT 10;
```

Load data: `python gcu/parse_gtsu_excel.py path/to/ГЦУ-MM-DD.xlsx`

---

## Open WebUI configuration

After starting, re-apply the model presets and tool server registration:

```bash
# Get admin token
TOKEN=$(curl -s -X POST http://localhost:3000/api/v1/auths/signin \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"yourpassword"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Register MCP server
curl -s -X POST http://localhost:3000/api/v1/configs/tool_servers \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"TOOL_SERVER_CONNECTIONS":[{"url":"http://gcu-mcp:8808/mcp","path":"mcp","type":"mcp","auth_type":"none","key":"","headers":null,"config":{"enable":true},"info":{"id":"gcu-postgres","name":"GCU Postgres"}}]}'
```

See `openwebui_config.json` for model presets and filter code.

---

## UI customizations (RZD branding)

From `static/`:
- **`custom.css`** — RZD red theme, dark sidebar, hides workspace/auth/suggestions/model names (32 sections)
- **`loader.js`** — strips "(Open WebUI)" from title, forces sidebar open, fixes splash logo
- **`rzd_logo.png`** — used as favicon, model avatar, and splash screen logo

Mounted as Docker volumes into the OWI container. No build step required.

---

## Native Windows deploy (without Docker)

See `launchers/` for `.cmd` scripts. Requirements:
- PostgreSQL 18 installed, data at `C:\DB_DATA`
- Open WebUI venv at `c:\llm\openwebui\.venv`
- Set env var `POSTGRES_PASSWORD` before running

Scheduled tasks (persist across reboots):
```
OpenWebUI     — logon trigger, runs launch_openwebui.cmd
GCU_MCP       — logon trigger, runs run_mcp.cmd
GCU_Watch     — logon trigger, runs run_watch.cmd
```

Autologon configured for `user` account (`HKLM\...\Winlogon`).

---

## Known limitations

- **LM Studio cannot be containerized** — it's a GUI Electron app that holds the GPU directly. The local 9B model always runs natively on the host.
- **9B doesn't make native tool calls** through Open WebUI 0.9.5 for local LM Studio connections — the tool call loop doesn't execute. Uses filter injection instead.
- **Remote 27B requires agentplatform.ru** (or another OpenAI-compatible API that supports native function calling).
