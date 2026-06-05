# ЦГЦУ AI Assistant — Full Handoff & Code Guide

**Repo:** `iskandaryv/6EE3PKHeeUSCKx` (private). Working dir: `C:\llm\gcu-export`.
**Push:** `git push https://iskandaryv:<TOKEN>@github.com/iskandaryv/6EE3PKHeeUSCKx.git master:master`
**What it is:** Local AI analyst for РЖД daily ГЦУ operational reports. Open WebUI + Postgres + MCP + LM Studio, all Dockerized, РЖД-branded.

---

## 1. Architecture — 5 Docker containers (`docker compose` in `C:\llm\gcu-export`)

| Container | Port | Role |
|---|---|---|
| `gcu-postgres` | 5432 (internal) | postgres:16, volume `postgres-data`. Holds `gtsu_search` (21912 rows, 31 March-2022 dates) + views + dicts |
| `gcu-mcp` | 8808 | MCP server (`gcu/mcp_postgres_server.py`), 4 tools. Built w/ host-header patch (Dockerfile.mcp) |
| `gcu-openwebui` | 3000 | ghcr.io/open-webui/open-webui:main. Config in container `webui.db` (SQLite) |
| `gcu-upload` | 8810 | Standalone xlsx→PG uploader (`gcu/upload_server.py`), Flask |
| `gcu-watch` | — | Silent auto-parse of ГЦУ .xlsx dropped in OWI uploads |

**Data flow:** User → OWI (:3000) → model (LM Studio :1234 local OR agentplatform.ru API) → MCP (:8808) → Postgres.
**Host:** RTX 5090 Laptop **24 GB VRAM**, 31 GB RAM, Intel Ultra 9 275HX. LM Studio serves :1234 (`lms` CLI at `C:\Users\Iskandar\.lmstudio\bin\lms.exe`).

---

## 2. The DATA model (gtsu_search) — semantics that matter

Flat table, one row per (date × indicator-leaf). Key columns:
- `report_date`, `section_code` (I/II/III-forecast), `item_number` ("1.1.7"), `item_depth` (1=раздел, 3=лист)
- `parent_path` = тема/категория (e.g. "1. СКОРОСТЬ ДОСТАВКИ…"); `indicator` = лист (often the OBJECT: дорога name); `full_indicator` = parent>indicator
- `responsible` = dept code (ЦД, ЦТ, ЦФТО…) — **NOT** the road
- `color_marker`: **2=КРАСНАЯ, 1=ЖЁЛТАЯ, 0=ЗЕЛЁНАЯ, 4=особая/информац., NULL=нет**
- `metrics` JSONB — **Russian keys only**: `факт_сутки, сутки_к_плану, сутки_к_2021, факт_месяц, месяц_к_плану, месяц_к_2021, факт_год, год_к_плану, год_к_2021` + invest keys `ввод_фондов_*`, `инвест_затраты_*`
- **Отклонения = доли** (-0.0979 = -9.79%). **факт_месяц/факт_год = нарастающим итогом** (for rates like км/сут this is a running AVERAGE-to-date, NOT a sum — never multiply by days)

**Hierarchy gotcha (A1):** per-road breakdown = CHILD rows; `indicator`=road, тема in `parent_path`. Search by `full_indicator ILIKE`, NOT `indicator` alone (which only matches the zero aggregate-placeholder).

---

## 3. DB views & dicts (the "decode layer") — `db/setup_db.sql` (idempotent, run after dump)

These live in the postgres VOLUME — **re-apply after any volume rebuild**:
```bash
docker exec -i gcu-postgres psql -U postgres -d postgres < db/gtsu_search_dump.sql   # 21912 rows
docker exec -i gcu-postgres psql -U postgres -d postgres < db/setup_db.sql           # comments+views+dept_codes
```
- **`gtsu`** view: typed columns (`факт_сутки`, `факт_месяц_нараст`, `факт_год_нараст`), отклонения already `%` (`откл_*_pct`), `зона` as text. Use for NUMERIC questions instead of raw JSONB. **NOT a precomputed answer** — Postgres runs it live each query; auto-covers new daily uploads.
- **`gtsu_catalog`** view: distinct indicator/breakdown rows — "what разрезы exist".
- **`dept_codes`** table (143 rows): code↔name dict (ЦБС→Бухгалтерская служба). Agent JOINs on demand; 28/39 DB codes covered, 11 gaps left as bare codes (no hallucination). Source: `db/dept_codes.sql`.
- **Column comments** (`db/seed_comments.sql`): surfaced by `describe`, carry the semantics above.

**CRITICAL fact-check that corrected the external review:** the doc's `WHERE full_indicator NOT ILIKE '%Доработка системы-источника%'` junk-filter would DELETE 496 REAL per-road speed rows. Only the 31 depth<3 parent aggregates are empty. **The gtsu view does NOT filter by that name.**

---

## 4. MCP tools (`gcu/mcp_postgres_server.py`, port 8808)

- **`describe(table='')`** — live schema introspection: columns+types+comments, ranges, low-cardinality value lists, JSONB keys, real samples. Advertises the `gtsu`/`gtsu_catalog`/`dept_codes` relations (dynamic, not hardcoded). Call FIRST / when 0 rows.
- **`query(sql)`** — read-only SELECT/WITH. `_run_select` blocks INSERT/UPDATE/etc.
- **`current_datetime(timezone='Europe/Moscow')`** — fixes the hallucinated date (zoneinfo). 
- **`weather(city='Москва')`** — Open-Meteo (no key; wttr.in timed out, replaced).

OWI tool name presented to model = `gcu-postgres_query` etc. Rebuild after edits: `docker compose up -d --build gcu-mcp`.

---

## 5. Models (in OWI `webui.db`, set via `db/*.py` scripts run inside the container)

4 active presets (all `function_calling=native`, `toolIds=['server:mcp:gcu-postgres']`):
- **ЦГЦУ Ассистент 27Б** (remote, base `ap.qwen/qwen3.6-27b`) — API, best/most reliable
- **ЦГЦУ Ассистент 27Б (локальный)** (LM Studio `qwen/qwen3.6-27b`)
- **ЦГЦУ Ассистент 9Б** (remote `ap.qwen/qwen3.5-9b`)
- **ЦГЦУ Ассистент 9Б (локальный)** (LM Studio `qwen/qwen3.5-9b`)
- **ЦГЦУ Кодер 32Б (локальный)** (`qwen2.5-coder-32b-instruct`) — ⚠️ ADDED but FAILS (see §7)

**System prompt** (in `params.system`, built up by idempotent `db/*.py` scripts, each guards w/ a sentinel):
- RU reasoning + formal style (no emoji) — `ru_reasoning.py`, `formal_style.py`
- Tools directive (call current_datetime/weather/describe/query) — `tools_directive.py`
- S4 blocks: ПЕРИОД И НАКОПЛЕНИЕ (A8) + ИЕРАРХИЯ И РАЗРЕЗЫ (A1) + САМОКОНТРОЛЬ — `patch_system_prompts.py` (parallel-session)
- **Analyst block was REMOVED** (`strip_analyst.py`) — user found it made outputs templated. SQL guidance to be studied later, NOT re-added as a prompt mandate.

**Live config exported to** `db/owi_config_export.json` (no secrets). **Connections:** [0] LM Studio `host.docker.internal:1234` (whitelist: the qwen models), [1] agentplatform `https://api.agentplatform.ru/v1` prefix `ap` (key in `.env`).

---

## 6. UI / branding (`static/custom.css` + `static/loader.js`, bind-mounted to `/app/build/static/`)

- Dark-graphite sidebar (#3a3a3e). loader.js: scrub "Open WebUI"→"РЖД Интер", build `#rzd-brand` header (REUSE OWI's favicon logo, hide the duplicate, enlarge 46px), footerProfile (avatar tile + green #rzd-live badge, name→"Оператор" via `db/set_brand.py`), uploadMenuItem (clones the Настройки row in user-menu → "Загрузить доклад" w/ red file icon, opens :8810).
- White-flash fix: force OWI's hardcoded light Tailwind classes (`from-white/via-white/bg-gradient-to-b/-t/group-hover:bg-white`) to transparent/dark inside #sidebar.
- Russian prompt suggestions (`db/ru_suggestions.py` → `config.ui.prompt_suggestions`), removed `DEFAULT_PROMPT_SUGGESTIONS` env.
- **The /static/ route is `/app/build/static/` NOT backend/** — mount both. Verify UI via headless Chrome `--virtual-time-budget=14000 --screenshot`; the remote-debug DOM probe returns "no sidebar" (SPA not hydrated).

---

## 7. KNOWN ISSUES / decisions (read before changing models)

1. **Coder-32B FAILS as an agent** (live-tested): never executes tool calls through OWI — prints `query_gcu_report(sql=...)` as TEXT, hallucinated "15" red-zone when真 answer is 88. Coder models write SQL, don't CALL tools. **For an agent use an INSTRUCT model, never a Coder.** Same applies to Coder-14B (don't get it).
2. **9B is weak at the agentic loop** — gives up after one SQL error, invents table names (`reports`, `docs`), fumbles `metrics->>'k'::numeric` precedence, mixes Latin+Cyrillic in identifiers. The views (`gtsu`) remove the JSONB-cast class of errors.
3. **OOM risk:** running LM Studio (17.8 GB) + a loaded model + a download OOM-killed all 5 containers (exit 137). Data safe. **Unload unused models in LM Studio.**
4. **Context sizing:** ГЦУ chats use ~8-15k tokens. Set local model to **32k** (not 256k — KV-cache eats ~10 GB at 256k). **Max Concurrent Predictions = 1** (was 4 — splits context, wastes VRAM).
5. **VRAM math (24 GB):** Q4 27B (17.5 GB)+32k fits. Q4 MoE 35B-A3B (22 GB) too tight → use **Q3_K_M (~17 GB)**. Q6/Q8 of 32B don't fit. MTP variant likely needs Unsloth Studio, not LM Studio — skip for now.

---

## 8. PENDING (next session)

1. **Wire + test the MoE `Qwen3.6-35B-A3B` (Q3_K_M)** when download finishes — it's the right "fast + smart + tool-calling" model (27B-quality at ~3B-active speed). Clone preset config from `db/add_coder32b.py` pattern (native FC + MCP tool bound + ЦГЦУ prompt). **MUST verify the tool-loop through OWI** (the test the Coder failed) — direct LM Studio test: `curl :1234/v1/chat/completions` with `tools=[query]`, check `finish_reason:tool_calls`. Then end-to-end via OWI `/api/chat/completions` (needs api_key, `chat_id` field required) and confirm MCP logs show the query ran + answer matches DB.
2. **Decide fate of Coder-32B preset** — probably remove it (it fails).
3. **Before/after test analysis** — user is testing questions; pull chats from `webui.db` (`SELECT chat FROM chat`), count invented-table + JSONB-cast errors vs baseline (~60 errors/179 calls), fact-check answers vs Postgres.

---

## 9. HOW TO TEST / FACT-CHECK (the method that matters)

- **Pull chat logs:** inside container, `sqlite3 /app/backend/data/webui.db` → `SELECT title, chat FROM chat ORDER BY updated_at DESC` → parse `history.messages`, extract SQL from tool-call detail blocks, the `Ошибка:` strings, final text.
- **Fact-check every numeric answer against Postgres** — e.g. red-zone count on 2022-03-01 = **88**; per-road max speed 03-01 = **Дальневосточная 1368.556**, min = Октябрьская 358.365. The model has hallucinated counts before — always verify.
- **Only March 2022 data exists** (03-01..03-31). April questions correctly = "нет данных" (a valid test).
- **Test on the weak model** (9B/local) — that's where errors concentrate.

---

## 10. Credentials / secrets (in `.env`, gitignored but force-pushed to private repo)
- POSTGRES_PASSWORD=Gcu2026! · agentplatform key sk-ap-… · GitHub PAT ghp_… (in chat history — rotate when done)
- OWI: WEBUI_AUTH=False (no login); auto-admin `admin@localhost`. ENABLE_API_KEYS gotcha: it's `auth.enable_api_keys` (plural) PersistentConfig, env `ENABLE_API_KEYS`.
- DB datetime gotcha: `config` table uses DATETIME strings; writing int epoch to `config.updated_at` crash-loops OWI. `model`/`function` tables use int epoch.

---
*Generated end of 2026-06-05 session. Full architecture also in memory file gcu-assistant-architecture.md.*
