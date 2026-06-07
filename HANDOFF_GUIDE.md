# ЦГЦУ AI Assistant — Full Handoff & Code Guide

**Repo:** `iskandaryv/6EE3PKHeeUSCKx` (private). Working dir: `C:\llm\gcu-export`.
**Push:** `git push https://iskandaryv:<TOKEN>@github.com/iskandaryv/6EE3PKHeeUSCKx.git master:master`
**What it is:** Local AI analyst for РЖД daily ГЦУ operational reports. Open WebUI + Postgres + MCP + LM Studio, all Dockerized, РЖД-branded.

---

## 1. Architecture — 5 Docker containers (`docker compose` in `C:\llm\gcu-export`)

| Container | Port | Role |
|---|---|---|
| `gcu-postgres` | **5433 → 5432** | `pgvector/pgvector:pg16`, volume `postgres-data`. Holds the typed-column schema: `reports` (61 days = 31 March 2022 + 30 April 2026), `metrics` (20,056), `investment_metrics` (10,033), `report_comments` (15,395), `dept_codes` (143), `kb_chunks` (1,892), `report_sheets`, `audit_log`. **DBeaver:** host 127.0.0.1 port **5433** (the host's own Postgres holds 5432). |
| `gcu-mcp` | 8808 | MCP server (`gcu/mcp_postgres_server.py`), 4 tools. Built w/ host-header patch (Dockerfile.mcp) |
| `gcu-openwebui` | 3000 | ghcr.io/open-webui/open-webui:main. Config in container `webui.db` (SQLite) |
| `gcu-upload` | 8810 | Standalone xlsx→PG uploader (`gcu/upload_server.py`), Flask |
| `gcu-watch` | — | Silent auto-parse of ГЦУ .xlsx dropped in OWI uploads |

**Data flow:** User → OWI (:3000) → model (LM Studio :1234 local OR agentplatform.ru API) → MCP (:8808) → Postgres.
**Host:** RTX 5090 Laptop **24 GB VRAM**, 31 GB RAM, Intel Ultra 9 275HX. LM Studio serves :1234 (`lms` CLI at `C:\Users\Iskandar\.lmstudio\bin\lms.exe`).

---

## 2. The DATA model (typed schema v2) — semantics that matter

Rebuilt 2026-06-06 from the JSONB prototype. **Schema is `db/schema_v2.sql`** (idempotent;
re-applies cleanly). Parser is **`gcu/parse_gtsu_v2.py`** (writes typed columns, sha256
dedup, idempotent per file).

**Tables (FK chain: `reports.id ← report_sheets.report_id ← metrics/investment_metrics/report_comments`):**

- **`reports`** — one row per xlsx file. Columns: `report_date`, `sha256` (UNIQUE), `baseline_year` (2021 for March 2022, 2025 for April 2026 — for the `*_to_prev_year` columns), `metrics_count`, `red_count`, `yellow_count`, `green_count`, `status`.
- **`metrics`** — operational indicators (sheets «Доклад Ц ЦЗ» + «Срок доставки»). **All numbers in typed `float8` columns — no JSONB casting.**
  - `indicator_number` ("1.1.7"), `parent_indicator` ("1.1"), `section_roman`, `category`, `name`, `unit`
  - `responsible` (ЦД/ЦТ/ЦФТО/…), `road` (Октябрьская/Дальневосточная/… — null for non-road rows; indexed)
  - `zone` smallint **0=зелёная / 1=жёлтая / 2=красная / 4=особая** (CHECK constraint)
  - 9 numeric: `day_fact, day_to_plan, day_to_prev_year`, `month_*`, `year_*`. **Deviations are FRACTIONS (-0.0979 = -9.79%).** `*_fact` for month/year are нарастающим итогом — running totals (rates → averages-to-date, never sum).
  - `cell_ref` ("B14") for source traceability
  - Partial index `idx_metrics_problem (report_id, zone) WHERE zone IN (1,2)` → fast "red+yellow on date X"; russian FTS on `name`.
- **`investment_metrics`** — sheets «Инвест» + «Инвест Факт» (different shape, separate table). `code_spiui`, `program`, `is_forecast` bool, then expenses (`exp_approved_year`, `exp_period_plan`, `exp_fact_or_forecast`, `exp_pct_to_period`, `exp_pct_to_year`) and funds-commissioning (`funds_*`).
- **`report_comments`** — text commentary + management actions, separated from metrics so one indicator can have multiple comment rows. Russian FTS index over commentary+management_action.
- **`dept_codes`** (143 rows) — code↔name dictionary (ЦБС→Бухгалтерская служба). JOIN `metrics.responsible = dept_codes.code` (some codes have no dictionary entry; that's expected, no hallucination).
- **`kb_chunks`** (1,892 rows) — knowledge-base vectors (see §11).

---

## 3. Schema management

- **`db/schema_v2.sql`** — apply with `docker exec -i gcu-postgres psql -U postgres -d postgres < db/schema_v2.sql`. Idempotent (CREATE IF NOT EXISTS / OR REPLACE everywhere).
- **`db/dept_codes.sql`** — seed for the 143-row dictionary.
- **No views needed** — the typed columns are queryable directly. The old `gtsu`/`gtsu_catalog`/`gtsu_totals` views are gone (they existed to paper over the JSONB).
- **Bulk reload from the desktop folders:**
  ```bash
  docker cp "C:/Users/Iskandar/Desktop/март 22 — копия" gcu-watch:/tmp/march
  docker cp "C:/Users/Iskandar/Desktop/апрель 2026" gcu-watch:/tmp/april
  docker exec gcu-watch python /app/parse_gtsu_v2.py /tmp/march
  docker exec gcu-watch python /app/parse_gtsu_v2.py /tmp/april
  ```

---

## 4. MCP tools (`gcu/mcp_postgres_server.py`, port 8808)

- **`describe(table='')`** — live schema introspection: columns+types+comments (from the DB), ranges, low-cardinality value lists, real samples. Defaults to `metrics`. Other public-schema tables are listed by name only. Tool docstrings + the `describe` output are intentionally schema-only — **no example SQL, no dates, no prescriptive guidance** (those used to live there and biased the model; removed 2026-06-06).
- **`query(sql)`** — read-only SELECT/WITH. `_run_select` blocks INSERT/UPDATE/etc.
- **`current_datetime(timezone='Europe/Moscow')`** — fixes the hallucinated date (zoneinfo). 
- **`weather(city='Москва')`** — Open-Meteo (no key; wttr.in timed out, replaced).
- **`search_knowledge(query, k=4, collection='')`** — RAG over the railway literature (see §11). Model calls it ON DEMAND for normative/theory questions; numbers still go to `query`. Returns cited passages (ПТЭ verbatim). collection: ''=all, 'pte', 'textbooks'.

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

## 11. Knowledge Base (RAG over railway literature) — added 2026-06-05

**What:** the assistant can answer normative/theory questions from a library of railway
literature (ПТЭ + appendices + textbooks) with source citations — separate from the
structured ГЦУ data. The model calls `search_knowledge` ON DEMAND (not auto-attached →
no context bloat); ГЦУ-number questions still route to `query`. **Validated end-to-end:**
"красная зона 5 апреля"→`query`→51 (correct); "обязанности по ПТЭ"→`search_knowledge`→
cited ПТЭ разд.II п.5/п.7 verbatim.

**Pipeline (3 scripts + schema):**
1. `gcu/prepare_kb.py` — **Stage-0 prep.** Reads PDFs/DOCX (`Лит-ра для ИИ`), denoises
   (strips page numbers, repairs hyphenation), segments on REAL structure (ПТЭ: Roman
   разд. + numbered clauses; textbooks: dotted/ALL-CAPS headings), emits curated markdown
   "context-forms" with breadcrumbs + citations → `kb_out/{pte,textbooks}/*.md`.
   **ПТЭ = VERBATIM** (is_verbatim=true); textbooks cleaned + 1-line «О чём:» prefix.
   No-loss fallback emits whole-doc segment if no structure found. 47 files → 1682 segments.
2. `db/kb_schema.sql` — `kb_chunks` table: `vector(1024)` + HNSW(cosine) + russian FTS `tsv`.
   Needs **pgvector** image (see below).
3. `gcu/embed_kb.py` — embeds curated chunks via LM Studio → `kb_chunks`. Idempotent per
   source_file. **e5-large-INSTRUCT convention: passages BARE (`--no-prefix`)**, query gets
   the Instruct wrapper (in the MCP tool). 676 pte + 1006 textbooks = 1682 rows.
4. `search_knowledge` tool in `mcp_postgres_server.py` — embeds query (Instruct prefix),
   **hybrid retrieval = vector + russian FTS fused by RRF** (1/(60+rank)), returns top-k
   cited passages. Hybrid RRF was VERIFIED to route to the right doc/section (pure vector
   alone was imprecise — scores clustered 0.84–0.87).

**Embedder:** `text-embedding-multilingual-e5-large-instruct` in LM Studio (1024d). Prefix
test (margin right−wrong): Instruct-query+bare-passage = **0.133** (best) > query:/passage:
0.112 > none 0.094. The query-side prefix lives in `KB_QUERY_INSTRUCT` in the MCP server —
**must match** the passage-side convention in embed_kb.py for the SAME model.

**pgvector swap:** `postgres:16` → `pgvector/pgvector:pg16` (docker-compose). Data-safe
(same PG16, volume kept — verified 22264 rows survived). One gotcha: collation-version
warning after swap → `ALTER DATABASE postgres REFRESH COLLATION VERSION;` (done).

**Ops / re-runs:**
```bash
# prepare (offline, no model): in a container with pypdf
python gcu/prepare_kb.py <Лит-ра dir> --out kb_out
# embed (needs e5 loaded in LM Studio; UNLOAD the MoE first if VRAM tight):
python gcu/embed_kb.py kb_out --model text-embedding-multilingual-e5-large-instruct --dim 1024 --no-prefix
# rebuild tool: docker compose up -d --build gcu-mcp
```
**OOM note:** MoE (15.5 GB) + e5 (1 GB) co-loaded fits 24 GB. For a big re-embed, unload MoE.
**Known imperfections:** some textbook PDFs have in-word OCR spaces (`корреспонд ируют`) —
left as-is (de-spacing risks gluing real words); doesn't break hybrid retrieval. 3 ЕСТП
TOC/body duplicate chunks (harmless). Corpus gaps exist (e.g. no clean «участковая
скорость» definition) — that's missing source content, not a retrieval bug.

**Curated corpus** lives in `kb_out/` (7.5 MB, commit it — the real asset). Source PDFs
(`Лит-ра для ИИ`, 103 MB) need NOT be committed.

**Tuning applied 2026-06-05 (after first live tests):**
- **Context-lean retrieval:** `search_knowledge` default **k=3** (max 6), each returned
  chunk capped at **KB_SNIPPET_CHARS=600** (was 1100), whitespace folded. One search now
  ≈300 tokens (was ~4-5K). Reason: a multi-search question once ate the whole 4K window.
- **`reference` collection (curated справки) with ranking BOOST:** small authoritative docs
  embedded as `collection='reference'`, tagged `[СПРАВКА (курируемая)]`, get +0.010 RRF so
  they outrank general textbook chunks. First member: **`Срок доставки (факторы).docx`** (8
  factor-groups) — now the top hit for «причины/факторы отставания поездов». Prep it with
  `prepare_kb.py <file> --collection reference` (single-int «N. Заголовок» segmenter).
- **KB routing directive** (`db/kb_directive.py`): adds a «БАЗА ЗНАНИЙ» block to every active
  preset's system prompt telling the model to call `search_knowledge` for normative/theory/
  ПРИЧИНЫ questions (it was answering causes from gtsu SQL comments and never searching).
  Verified: the причины-отставания question now routes to the KB and cites the факторы doc.
- **MoE reasons in English** despite the top-of-prompt Russian-`<think>` rule — known Qwen-MoE
  bias; final answer is correct Russian. Decided NOT worth extra prompt overhead to fight.
- **Context-length gotcha:** the MoE must be loaded at a large context (use **64K**); LM
  Studio's JIT default of 4096 causes "Context size exceeded" on the very first message
  (system prompt + tools + a KB result alone exceed 4K). Save 65536 as the model's default
  in LM Studio so a reload doesn't drop back to 4K.

---

## 12. Session 2026-06-06 — schema v2, KB expansion, fuzzy search, model-ceiling finding

### 12.1 Schema v2 migration (BREAKING — replaces gtsu_search)
The legacy single-table `gtsu_search` JSONB prototype is **gone**. New normalized model in
**`db/schema_v2.sql`** (idempotent), populated by **`gcu/parse_gtsu_v2.py`**:
- **`reports`** — one row per xlsx (date, baseline_year, sha256-dedup, red/yellow/green counts).
- **`report_sheets`** — one row per sheet.
- **`metrics`** — one row per indicator leaf, OPERATIONAL sheets only (Доклад Ц ЦЗ + Срок
  доставки). Typed columns (no JSONB): `indicator_number`, `parent_indicator`, `name`,
  `unit`, `day_fact`, `month_fact`, `*_to_plan`, `*_to_prev_year`, `zone`, `responsible`,
  `text_comment`, **`populates`** (so callers filter cumulative-only indicators explicitly
  instead of guessing on NULL `day_fact`).
- **`investment_metrics`** — Инвест sheets (different shape, kept separate).
- **`report_comments`** — free-text comment rows.
- Cleanup: dropped dead columns (subcategory, raw_data, audit_log, reports.status/error_message
  — all 0% used after a full 61-day load).
- **Deleted (old v1):** `db/setup_db.sql`, `db/gtsu_views.sql`, `db/gtsu_search_dump.sql`,
  `db/seed_comments.sql`, `gcu/create_gtsu_db.py`, `gcu/parse_gtsu_excel.py`, `gcu/gcu_filter.py`,
  `gcu/querytool.py`, `gcu/openapi_sql_server.py`. (The MCP `query`/`describe` tools now target
  `reports`/`metrics`.)

### 12.2 April 2026 data loaded
All 30 April days ingested (+10,559 rows). DB now holds **March 2022 (31 days) + April 2026
(30 days) = 61 reports, 20,056 metrics**. Note the source quirks surfaced (questions for the
ЦГЦУ interview): April compares **«к 2025»** (March was «к 2021»); many indicators are
**cumulative-only** (`day_fact` NULL, only `*_year` populated — e.g. скорость доставки);
no **«на больничном»** indicator exists in these files.

### 12.3 KB grew to 1,892 chunks across 4 tiers
| Collection | Chunks | What | Cap |
|---|---|---|---|
| pte | 676 | ПТЭ + appendices (verbatim) | 2600 |
| textbooks | 1006 | Railway textbooks | 600 (trim hard) |
| reference | 8 | `Срок доставки (факторы).docx` (boosted) | 4000 |
| glossary | 202 | **`Аббревиатуры РЖД.pdf`** — telegraph-code directory (boosted) | 2500 |
- **`glossary`** (new) decodes the codes that litter the data: Ц, ЦЗ-1, ЦЗ-ЦТ, ЦФТО, ЦБС,
  ДЦУП… and the Аппарат управления structure. New `segment_glossary()` in `prepare_kb.py`
  (`--collection glossary`) keeps each org-unit's role→code block whole.
- **`reference`/`glossary` get +0.010 RRF boost** so curated authoritative docs outrank
  general textbook chunks.
- **Per-collection truncation caps** (`KB_CAPS` in the MCP server) replaced the single
  600-char cap: textbooks stay lean (600, bloat lives there), but glossary/pte/reference come
  back whole so «перечисли всё» questions get complete lists. Fixed the bug where the 600-cap
  cut the «Руководство ОАО РЖД» chunk to ~⅓ (model saw 6 of 19 roles).
- **Grounding rule** (`db/kb_grounding.py`, «ОПОРА НА ИСТОЧНИКИ»): even with full data the MoE
  was answering structure from its **training memory** (generic dept names, 0 codes). The rule
  forces "answer STRICTLY from retrieved fragments; quote exact names/codes; if fragments don't
  cover it, say so". Verified: 0 → 18 real codes in the answer.

### 12.4 Trigram fuzzy name search (real win, kept)
Indicator names are heavily **abbreviated** in the source («груз.», «в т.ч.», «установл.»,
«собл.»), so the model fished with 2-7 `ILIKE`-by-word attempts per question (model guessed
`%грузовых отправок%` → 0 rows; reality `%груз. отправок%` → 90 rows).
- **`CREATE INDEX idx_metrics_name_trgm ON metrics USING gin (name gin_trgm_ops)`** (in
  `schema_v2.sql`) → fast `name % 'запрос'` / `ORDER BY similarity(name,'…') DESC`.
- **`describe('metrics')`** now appends two facts: the **report_date range** (so the model
  stops guessing empty dates like May 2026) and the **abbreviation + fuzzy-search hint**.
Result: name-discovery fishing eliminated (Q2 found классы via `name % 'класс'` immediately
vs 7 ILIKE attempts).

### 12.5 Show only the MoE in OWI
**`db/show_only_moe.py`** (idempotent, reversible — hides, never deletes): deactivates all
presets except «ЦГЦУ Ассистент 35Б MoE (локальный)», trims the LM Studio whitelist to just
`qwen3.6-35b-a3b`, disables the API (agentplatform) connection. Dropdown now shows one model.

### 12.6 Honest finding — a MODEL CEILING, not a config bug
After fixing name-fishing, the bottleneck **moved**: the Qwen 35B MoE **re-runs the identical
data query 4-6× before answering** (saw `SELECT … month_fact WHERE report_date>='2026-04-01'`
repeated 5× in one trace). No prompt/DB line stops it. Across prompt/schema variants
(v2 7/10, v2.1 6/10, v3 7/10, v3.1+trigram 8/15) the re-query loop persists on hard multi-step
analytical questions; **simple operational questions are clean and numbers are accurate**.
The trigram + describe + grounding fixes are real, general improvements — keep them. Remaining
levers (NOT yet done): a **harness-level guard** that detects a repeated identical query and
injects "you already have this — answer now"; a **larger dense model** (27B follows
instructions better per March notes); or **accept 8/15 on hard analytics and ship** (the bulk
of real operational use works).

### 12.7 Pending
- Harness dup-query guard (the only untried lever that might lift the hard-question ceiling).
- Decide model: keep MoE (fast, wanders on multi-step) vs dense 27B (slower, more obedient).
- ЦГЦУ interview (human task) on indicator semantics — see 12.2 quirks.

---

## 13. Session 2026-06-07 — benchmarks (Gemma 26B + 102Q), dup-query guard, справки-источники queries

### 13.1 Benchmarks run & scored
- **Gemma 26B a4b-qat** wired into OWI as «ЦГЦУ Ассистент Gemma 26Б (локальный)» (`db/add_gemma.py`).
  15Q result: **7/15 genuine** (3 lazy 0-call refusals, same re-query ceiling as Qwen). Qwen wins on accuracy
  (8/15) AND speed (1.63 s/call vs 2.80 s/call for Gemma). Gemma's 3 refusals are model-specific.
- **Qwen 40Q full benchmark**: 18/40, 10.0 min total. Detailed group analysis documented
  (`db/benchmark_qwen35moe_40.md` + `db/Бенчмарк_Qwen35MoE_40.docx`).
- **15Q question list** extracted to `db/questions_15.txt` for sharing.

### 13.2 Dup-query guard (in `mcp_postgres_server.py`)
Added graduated ring-buffer guard: 3rd identical SQL → WARN, 4th → BLOCK with "answer now" message.
Window=12 recent queries, no TTL. Tested: 40Q run with guard → 4 new wins, 4 regressions (all regressions
due to LLM non-determinism, guard fired 0 times on them — confirmed by per-Q ring simulation).
Net impact is positive; final stats need 3-run average to eliminate variance at temp=0.2.

### 13.3 GCU-2026-03-12.xlsx loaded
The ГЦУ доклад for 2026-03-12 was 0 bytes (copy error). Fixed and loaded: **299 metrics, 58 red,
97 yellow**. DB now: 62 reports (2022-03-01 … 2026-04-30), 20,355 metrics.

### 13.4 Справки-источники (5 tables, loaded for 2026-03-12)
`db/spravki_schema.sql` + `gcu/parse_spravki.py` → 5 queryable tables linked by `report_date`:
| Table | Rows | What |
|---|---|---|
| `spravki_delays` | 96 | Detained trains by delay-code + road (12.03.2026) |
| `spravki_failures` | 45 | Equipment failures 1-2 cat. by dept (12.03.2026) |
| `spravki_locomotives` | 29 | Locomotive fleet plan/fact by polygon (12.03.2026) |
| `spravki_port_stations` | 163 | Port stations ДВОСТ/ОКТ/СКАВ (12.03.2026) |
| `spravki_speed` | 34 | Section + technical speed by road (12.03.2026) |
`describe('metrics')` now shows all 5 tables with routing hints. Model can now answer:
«задержано поездов по коду 21 на 12.03» → **22 trains / 1405 wagons** (direct SQL).
To ingest new dates: `python gcu/parse_spravki.py --date YYYY-MM-DD --dir /path/to/справки`

### 13.5 102Q comprehensive benchmark (running)
`db/questions_100.py` (102 questions across 9 groups A–I) + `db/test_runner_100.py`.
Groups: A=delays, B=personnel, C=freight work, D=failures/schedule, E=finance,
F=knowledge-base, G=spravki-sources, H=hard analytical SQL, I=honest-refusal cases.
Sources: Обзраз2.docx, Вопросы по Срокам доставки.docx, Вопросы по Персоналу.docx,
existing 40Q set, session questions, 10 deliberately hard SQL questions.

### 13.6 Pending
- 102Q benchmark results + Word report (running as of 2026-06-07 session end).
- Harness dup-query guard re-test at temperature=0.0 for clean before/after comparison.
- Load спр авки-источники for April 2026 dates (same format, parser ready).
- Indicator_number non-uniqueness warning in `describe()` (causes Q1 loop — quick fix).

---
*Extended 2026-06-07. Справки integration, dual benchmark (Gemma + Qwen 102Q), dup-query guard.*
