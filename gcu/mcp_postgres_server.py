# -*- coding: utf-8 -*-
"""
GCU Postgres MCP Server — Streamable HTTP transport.

A minimal MCP server that exposes a `query` tool for read-only SQL against the
local PostgreSQL (reports / metrics / investment_metrics / report_comments,
plus the knowledge base kb_chunks). Speaks the Streamable HTTP protocol that Open WebUI
v0.6.31+ expects natively.

Run:
    set PGPASSWORD=Gcu2026!
    c:\llm\openwebui\.venv\Scripts\python.exe mcp_postgres_server.py

Then in Open WebUI Admin → External Tools → Add Server:
    Type: MCP (Streamable HTTP)
    URL:  http://localhost:8808/mcp
    Auth: None
"""
import os
import re
import sys
import asyncio

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # psycopg cannot run async on the default ProactorEventLoop; switch to
    # the selector policy. (Belt-and-suspenders: the query tool below is also
    # synchronous, so it works regardless of which loop uvicorn installs.)
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# Must set BEFORE importing FastMCP (pydantic-settings reads env at class definition)
os.environ.setdefault("FASTMCP_HOST", "0.0.0.0")
os.environ.setdefault("FASTMCP_PORT", "8808")

from mcp.server import FastMCP

# Create the MCP server
mcp = FastMCP(
    "GCU Postgres",
    instructions="PostgreSQL — ежедневные доклады ГЦУ ОАО РЖД.",
)

DB_URL = os.environ.get(
    "GCU_DATABASE_URL",
    "postgresql://postgres:Gcu2026!@127.0.0.1:5432/postgres"
)


DEFAULT_TABLE = os.environ.get("GCU_TABLE", "metrics")

_FORBIDDEN = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT", "MERGE")


def _run_select(sql, limit_rows=50):
    """Execute a single read-only SELECT and return a text table (or error string)."""
    import psycopg

    clean = sql.strip().rstrip(";")
    if not clean.upper().startswith(("SELECT", "WITH")):
        return None, "Ошибка: разрешены только SELECT-запросы."
    upper_tokens = set(clean.upper().replace("(", " ").replace(",", " ").split())
    for word in _FORBIDDEN:
        if word in upper_tokens:
            return None, f"Ошибка: запрещена операция {word}."

    try:
        with psycopg.connect(DB_URL, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(clean)
                if not cur.description:
                    return [], "Запрос выполнен (без результата)."
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
                return (cols, rows), None
    except Exception as e:
        return None, f"Ошибка: {e}"


def _fmt_table(cols, rows, limit_rows=50):
    if not rows:
        return "Запрос выполнен, данных не найдено."
    lines = [" | ".join(cols), "-" * min(80, len(" | ".join(cols)))]
    for row in rows[:limit_rows]:
        lines.append(" | ".join(str(v) if v is not None else "-" for v in row))
    if len(rows) > limit_rows:
        lines.append(f"... (всего {len(rows)} строк, показано {limit_rows})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dup-query guard — breaks the "re-run the SAME SELECT 4-6 times" loop that
# caps out small MoE models (15/22 failures in the 40Q benchmark). Graduated:
# the 3rd identical query gets a warning, the 4th+ is refused (data withheld)
# so the model is forced to ANSWER from data it already has.
#
# State is a bounded ring buffer of recent normalized-query hashes — GLOBAL,
# no TTL, but self-evicting (old queries fall out as new distinct ones arrive),
# so it can never grow unbounded or stale-trigger on a long-idle hash.
# ---------------------------------------------------------------------------
import hashlib
from collections import deque

_QGUARD_WINDOW = 12          # how many recent queries we remember
_QGUARD_WARN_AT = 2          # Nth identical (0-based prior count) -> warn
_QGUARD_BLOCK_AT = 3         # Nth identical -> withhold data
_recent_q = deque(maxlen=_QGUARD_WINDOW)   # holds normalized-sql md5 hashes

# Zero-result fishing guard: counts CONSECUTIVE queries that returned 0 rows.
# Resets on any query that returned rows. After 2 in a row, refuse with an
# instruction to stop name-fishing and answer from previous results. Catches
# the case where model rewrites the WHERE clause each turn (different SQL hash
# every time, so the identical-query guard above can't see the pattern).
_consec_zero = [0]   # list so we can mutate from inside functions
_ZERO_BLOCK_AT = 2

# Describe-loop guard: counts TOTAL describe() calls per question. Schema doesn't
# change mid-question, so calling describe more than twice (e.g. metrics+reports
# alternating, or one table re-described) is a wandering-loop signal. The
# identical-call guard above only catches verbatim repeats; this catches the
# alternating pattern (metrics→reports→metrics→spravki_delays etc.).
_describe_calls = [0]
_DESCRIBE_BLOCK_AT = 2

# Query-volume / wandering guard: counts TOTAL query() calls per question,
# regardless of whether the SQL is unique or returns rows. This is the missing
# lever behind "the model gets stuck": cap-hit traces issue 6-8 DIFFERENT,
# non-zero queries (each dodges the identical-query and zero-result guards) and
# never commit to an answer — the model already has the data by query 3-4 but
# keeps re-exploring metrics/spravki until the turn cap. Answered questions use
# ≤3 queries (avg 1.3); cap-hits average 6.5. After _QVOL_WARN we nudge, after
# _QVOL_BLOCK we hard-stop with "answer from what you have".
_query_calls = [0]
_QVOL_WARN = 4    # 5th query -> nudge
_QVOL_BLOCK = 6   # 7th query -> hard stop


def _qnorm(sql):
    """Normalize SQL so cosmetic differences don't dodge the guard."""
    return " ".join(sql.lower().strip().rstrip(";").split())


def _qguard_check(sql):
    """Return (level, prior_count). level: 0=ok, 1=warn, 2=block.
    Records this query in the ring buffer as a side effect."""
    h = hashlib.md5(_qnorm(sql).encode("utf-8")).hexdigest()
    prior = _recent_q.count(h)
    _recent_q.append(h)
    if prior >= _QGUARD_BLOCK_AT:
        return 2, prior
    if prior >= _QGUARD_WARN_AT:
        return 1, prior
    return 0, prior


@mcp.tool()
def describe(table: str = "") -> str:
    """Возвращает структуру таблицы: колонки с типами и комментариями,
    число строк, диапазоны/образцы значений.

    :param table: имя таблицы (по умолчанию — основная таблица)
    :return: текстовое описание схемы
    """
    import psycopg

    # FIX 1: guard on describe — same ring-buffer logic as query().
    # Prevents the model from calling describe('metrics') 9× in a row.
    tbl_key = f"__describe__{(table or DEFAULT_TABLE).strip()}"
    level, _ = _qguard_check(tbl_key)
    if level == 2:
        return ("⛔ СТОП: describe для этой таблицы уже вызывался несколько раз. "
                "Схема не изменилась. Используй уже полученную информацию и пиши SQL-запрос.")

    # FIX 5: total describe call cap per question. Catches the alternating
    # pattern (metrics → reports → metrics → spravki_delays) where each call
    # is "new" to the identical-call guard but the model is wandering.
    _describe_calls[0] += 1
    if _describe_calls[0] > _DESCRIBE_BLOCK_AT:
        _describe_calls[0] = 0   # reset so user can resume after the block
        return ("⛔ СТОП: describe уже вызывался " + str(_DESCRIBE_BLOCK_AT) +
                " раз(а). Схема не меняется. Используй уже полученную информацию "
                "и переходи к find_indicator + query. Если не знаешь куда смотреть — "
                "вызови find_indicator('смысл вопроса') и работай с возвращёнными именами.")

    tbl = (table or DEFAULT_TABLE).strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", tbl):
        return "Ошибка: недопустимое имя таблицы."

    try:
        with psycopg.connect(DB_URL, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                # 1) columns + types + per-column comments (all from the live catalog)
                cur.execute(
                    """
                    SELECT c.column_name, c.data_type,
                           col_description(%s::regclass, c.ordinal_position) AS comment
                    FROM information_schema.columns c
                    WHERE c.table_name = %s
                    ORDER BY c.ordinal_position
                    """,
                    (tbl, tbl),
                )
                cols = cur.fetchall()
                if not cols:
                    return f"Таблица «{tbl}» не найдена."

                tbl_comment = None
                cur.execute("SELECT obj_description(%s::regclass)", (tbl,))
                r = cur.fetchone()
                if r:
                    tbl_comment = r[0]

                cur.execute(f'SELECT count(*) FROM "{tbl}"')
                n_rows = cur.fetchone()[0]

                out = [f"Таблица/представление: {tbl} — строк: {n_rows}"]
                if tbl_comment:
                    out.append(f"Описание: {tbl_comment}")
                # List sibling tables — names only, no prescriptions, no examples.
                if tbl == DEFAULT_TABLE:
                    cur.execute(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema='public' AND table_type='BASE TABLE' "
                        "ORDER BY table_name"
                    )
                    others = [r[0] for r in cur.fetchall() if r[0] != tbl]
                    if others:
                        out.append("")
                        out.append("Другие таблицы в базе: " + ", ".join(others))
                    # Live FACTS only — no policy, no instructional prose, no hardcoded examples.
                    #   1. main report date range (so model doesn't guess empty dates)
                    #   2. coverage window for each spravki_* table (so it doesn't route
                    #      to a table that has no data for the asked date)
                    # All values come from the DB at call time — nothing typed here can rot.
                    try:
                        cur.execute(
                            "SELECT min(report_date), max(report_date), count(*) FROM reports")
                        dmin, dmax, ndays = cur.fetchone()
                        out.append("")
                        out.append(f"reports.report_date: {dmin} .. {dmax} ({ndays} дат)")

                        # spravki tables — name + live coverage window. No prose, no column
                        # hints (those are in each table's own describe()). The coverage window
                        # is the critical fact — without it the model confidently queries
                        # spravki_delays for April and gets 0 rows back.
                        cur.execute(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema='public' AND table_name LIKE 'spravki_%' "
                            "ORDER BY table_name")
                        spr_tables = [r[0] for r in cur.fetchall()]
                        if spr_tables:
                            out.append("")
                            out.append("Связанные таблицы-источники (детализация по report_date):")
                            for st in spr_tables:
                                try:
                                    # Coverage window — live, no hardcoding.
                                    cur.execute(f'SELECT min(report_date), max(report_date), count(DISTINCT report_date) FROM "{st}"')
                                    smin, smax, sndays = cur.fetchone()
                                    # Routing intent — first sentence of the table COMMENT in pg.
                                    # Single source of truth: the schema's own description, written
                                    # once at table creation. Auto-updates if you change the COMMENT.
                                    cur.execute("SELECT obj_description(%s::regclass)", (st,))
                                    desc_row = cur.fetchone()
                                    intent = ""
                                    if desc_row and desc_row[0]:
                                        intent = " — " + desc_row[0].split(".")[0].strip()
                                    if smin and smax:
                                        out.append(f"  • {st}: {smin} .. {smax} ({sndays} дат){intent}")
                                    else:
                                        out.append(f"  • {st}: пусто{intent}")
                                except Exception:
                                    conn.rollback()
                    except Exception:
                        conn.rollback()
                out.append("")
                out.append("КОЛОНКИ (тип — комментарий):")
                for name, dtype, comment in cols:
                    out.append(f"  • {name} ({dtype})" + (f" — {comment}" if comment else ""))

                # 2) per-column profile — only for columns the model actually needs to
                # know enumerated values for (road names, responsible codes, units).
                # Audit/internal columns (cell_ref, source_row, source_sheet, created_at,
                # indicator_number, parent_indicator, id, report_id, sheet_id) and all
                # pure numeric ranges are hidden — they add tokens without helping SQL writing.
                ОБРАЗЦЫ_SKIP = frozenset({
                    "id", "report_id", "sheet_id", "cell_ref", "source_row",
                    "source_sheet", "created_at", "indicator_number",
                    "parent_indicator", "is_priority", "section_roman",
                    "day_fact", "day_to_plan", "day_to_prev_year",
                    "month_fact", "month_to_plan", "month_to_prev_yr",
                    "year_fact", "year_to_plan", "year_to_prev_yr",
                    "zone", "populates", "name", "category",
                })
                out.append("")
                out.append("ЗНАЧЕНИЯ (для написания WHERE-условий):")
                for name, dtype, _ in cols:
                    if name in ОБРАЗЦЫ_SKIP:
                        continue
                    col = f'"{name}"'
                    try:
                        if dtype in ("date", "timestamp without time zone", "timestamp with time zone",
                                     "integer", "bigint", "numeric", "double precision", "real", "smallint"):
                            cur.execute(f"SELECT min({col}), max({col}), count(DISTINCT {col}) FROM \"{tbl}\"")
                            mn, mx, nd = cur.fetchone()
                            out.append(f"  • {name}: диапазон {mn} .. {mx} (различных: {nd})")
                        elif dtype in ("text", "character varying", "character"):
                            cur.execute(f"SELECT count(DISTINCT {col}) FROM \"{tbl}\"")
                            nd = cur.fetchone()[0]
                            if nd == 0:
                                continue   # empty column — don't waste tokens
                            if nd <= 40:
                                cur.execute(
                                    f"SELECT {col} FROM \"{tbl}\" WHERE {col} IS NOT NULL "
                                    f"GROUP BY {col} ORDER BY count(*) DESC LIMIT 40"
                                )
                                vals = [str(v[0])[:40] for v in cur.fetchall()]
                                out.append(f"  • {name}: {nd} различных значений: " + ", ".join(vals))
                            else:
                                cur.execute(
                                    f"SELECT {col} FROM \"{tbl}\" WHERE {col} IS NOT NULL "
                                    f"AND length({col}) BETWEEN 1 AND 60 ORDER BY random() LIMIT 6"
                                )
                                vals = [str(v[0])[:55] for v in cur.fetchall()]
                                out.append(f"  • {name}: {nd} различных, примеры: " + " | ".join(vals))
                        elif dtype == "jsonb":
                            cur.execute(
                                f"SELECT DISTINCT k FROM \"{tbl}\", "
                                f"LATERAL jsonb_object_keys({col}) AS k LIMIT 40"
                            )
                            keys = [str(v[0]) for v in cur.fetchall()]
                            out.append(f"  • {name}: ключи JSONB: " + ", ".join(keys))
                    except Exception:
                        # never let one column's profiling abort the whole description
                        conn.rollback()
                        continue
                return "\n".join(out)
    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool()
def query(sql: str) -> str:
    """Выполняет read-only SQL-запрос (SELECT/WITH) к PostgreSQL.

    :param sql: SQL SELECT/WITH (только чтение)
    :return: результат в текстовом виде
    """
    # Query-volume / wandering guard (the "gets stuck" fix). Fires BEFORE the
    # identical-query guard so it catches the case where every query is unique.
    _query_calls[0] += 1
    if _query_calls[0] > _QVOL_BLOCK:
        _query_calls[0] = 0   # reset so the model can resume after answering
        return ("⛔ СТОП: ты уже выполнил много запросов к БД по этому вопросу. "
                "Нужные данные почти наверняка уже среди полученных результатов. "
                "ПРЕКРАТИ запросы и сформулируй ОТВЕТ сейчас на основе того, что есть. "
                "Если какого-то одного числа действительно не хватает — назови ответ "
                "по имеющимся данным и укажи, чего именно не хватило. Не продолжай поиск.")

    # Anti-loop guard: catch the same SELECT being re-run instead of answering.
    level, prior = _qguard_check(sql)
    if level == 2:
        return ("⛔ СТОП: этот запрос уже выполнялся "
                f"{prior + 1} раз(а) с тем же результатом. Данные не изменятся. "
                "НЕ повторяй запрос — сформулируй ОТВЕТ на основе уже полученных "
                "данных. Если данных действительно не хватает, честно скажи, "
                "каких именно, и не зацикливайся.")

    # Zero-result fishing guard: refuse if previous N queries returned 0 rows.
    # Catches the name-fishing loop where each rewrite has a different hash.
    if _consec_zero[0] >= _ZERO_BLOCK_AT:
        _consec_zero[0] = 0   # reset so user can resume after the warning
        return ("⛔ СТОП: последние запросы возвращали 0 строк подряд. "
                "Это означает, что искомого показателя НЕТ в текущей таблице — "
                "ПЕРЕСТАНЬ перебирать формулировки. Дай честный ответ: "
                "«искомый показатель в БД не найден» и предложи ближайшие "
                "по смыслу из уже виденных результатов.")

    result, err = _run_select(sql)
    if err:
        return err
    cols, rows = result

    # update zero-result counter
    if len(rows) == 0:
        _consec_zero[0] += 1
    else:
        _consec_zero[0] = 0

    out = _fmt_table(cols, rows)
    if level == 1:
        out = ("⚠️ Внимание: ты уже выполнял ЭТОТ ЖЕ запрос — результат тот же. "
               "Переходи к ОТВЕТУ или измени запрос, не повторяй его снова.\n\n" + out)
    elif _query_calls[0] >= _QVOL_WARN:
        out = ("⚠️ Внимание: уже сделано несколько запросов. Скорее всего данных "
               "достаточно — переходи к ОТВЕТУ, а не к новым запросам.\n\n" + out)
    return out


# ---------------------------------------------------------------------------
# find_indicator — semantic search over indicator_index.
# Replaces the name-fishing pattern: instead of model rewriting WHERE clause
# with trigram/ILIKE patterns until something matches, it asks find_indicator
# by MEANING and gets the top-k actual names from metrics back. Source of
# truth is the metrics table — indicator_index is a derivative, rebuilt via
# gcu/build_indicator_index.py whenever new data is loaded.
# ---------------------------------------------------------------------------
_FIND_EMB_URL   = os.environ.get("KB_EMBED_URL",   "http://host.docker.internal:1234/v1/embeddings")
_FIND_EMB_MODEL = os.environ.get("KB_EMBED_MODEL", "text-embedding-multilingual-e5-large-instruct")
# e5-large-instruct convention: queries wrapped with instruction prefix.
_FIND_INSTRUCT  = "Instruct: Given a question about a metric, retrieve the indicator name\nQuery: "


def _embed_q(text):
    """Embed user query for find_indicator. Wraps with Instruct prefix."""
    import json as _json
    import urllib.request as _u
    payload = {"model": _FIND_EMB_MODEL, "input": [_FIND_INSTRUCT + text]}
    req = _u.Request(_FIND_EMB_URL, data=_json.dumps(payload).encode("utf-8"),
                     headers={"Content-Type": "application/json"})
    with _u.urlopen(req, timeout=60) as r:
        return _json.load(r)["data"][0]["embedding"]


_find_calls = [0]   # counter — find_indicator calls per conversation
_FIND_MAX = 2       # after 2 calls, refuse and force the model to pick


@mcp.tool()
def find_indicator(query: str, k: int = 5) -> str:
    """Семантический поиск показателя в metrics по СМЫСЛУ запроса.

    Используй это ВМЕСТО name % 'слова' или name ILIKE '%слова%' — даёт более
    точные результаты по неточным/перефразированным запросам. Возвращает топ-k
    реальных имён показателей с их типичным indicator_number, разделом и единицей.
    После получения списка — выбирай подходящее name и используй ТОЧНОЕ значение
    в WHERE name = '...' для query().

    :param query: вопрос или ключевое выражение на русском (например
                  'задержанные отправки', 'участковая скорость', 'погрузка угля')
    :param k: сколько вариантов вернуть (1-10, по умолчанию 5)
    :return: список кандидатов с метаданными
    """
    import psycopg

    # Anti-loop: don't let the model re-search with rephrased queries forever.
    # The first call returns 5-10 good candidates — that's enough information.
    _find_calls[0] += 1
    if _find_calls[0] > _FIND_MAX:
        _find_calls[0] = 0   # reset so user can resume
        return ("⛔ СТОП: find_indicator уже вызывался " + str(_FIND_MAX) +
                " раз(а). ВЫБЕРИ один из ранее возвращённых кандидатов и сделай "
                "SQL-запрос через query(). Если ни один не подходит — дай честный "
                "ответ «искомого показателя в БД нет», не перебирай формулировки.")

    k = max(1, min(int(k), 10))
    try:
        vec = "[" + ",".join(f"{x:.7g}" for x in _embed_q(query)) + "]"
    except Exception as e:
        return f"Ошибка эмбеддинга запроса: {str(e)[:160]}"

    try:
        with psycopg.connect(DB_URL, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT name, example_inum, example_section, example_unit,
                           n_occurrences, has_road,
                           1 - (embedding <=> %s::vector) AS sim
                    FROM indicator_index
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """, (vec, vec, k))
                rows = cur.fetchall()
    except Exception as e:
        return f"Ошибка поиска: {str(e)[:200]}"

    if not rows:
        return ("Индекс пуст. Запусти gcu/build_indicator_index.py чтобы построить.")

    out = [f"Топ-{len(rows)} кандидатов (по семантическому сходству):"]
    out.append("")
    for name, inum, section, unit, n_occ, has_road, sim in rows:
        road_tag = " [есть разбивка по дорогам]" if has_road else ""
        out.append(f"  sim={sim:.3f}  inum={inum}  раздел={section}  ед={unit}{road_tag}")
        out.append(f"    name = «{name}»")
    out.append("")
    out.append("ИСПОЛЬЗУЙ name дословно в WHERE m.name = '...' (не через ILIKE/%).")
    return "\n".join(out)


_WDAY_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_MON_RU = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря"]


@mcp.tool()
def current_datetime(timezone: str = "Europe/Moscow") -> str:
    """Возвращает текущую дату и время в указанном часовом поясе (IANA).

    :param timezone: имя зоны IANA (по умолчанию Europe/Moscow)
    :return: дата и время по-русски
    """
    import datetime as dt
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo(timezone))
        tzname = timezone
    except Exception:
        now = dt.datetime.utcnow()
        tzname = "UTC"
    return (f"Сегодня {now.day} {_MON_RU[now.month]} {now.year} года, "
            f"{_WDAY_RU[now.weekday()]}. Время: {now.strftime('%H:%M')} ({tzname}).")


@mcp.tool()
def weather(city: str = "Москва") -> str:
    """Возвращает текущую погоду в городе (источник: open-meteo.com).

    :param city: название города (по умолчанию Москва)
    :return: краткая сводка погоды
    """
    import json
    import urllib.parse
    import urllib.request

    WMO = {
        0: "ясно", 1: "преимущественно ясно", 2: "переменная облачность", 3: "пасмурно",
        45: "туман", 48: "изморозь", 51: "лёгкая морось", 53: "морось", 55: "сильная морось",
        61: "небольшой дождь", 63: "дождь", 65: "сильный дождь",
        66: "ледяной дождь", 67: "сильный ледяной дождь",
        71: "небольшой снег", 73: "снег", 75: "сильный снег", 77: "снежная крупа",
        80: "ливень", 81: "сильный ливень", 82: "очень сильный ливень",
        85: "снежный ливень", 86: "сильный снежный ливень",
        95: "гроза", 96: "гроза с градом", 99: "сильная гроза с градом",
    }

    def _get(url):
        req = urllib.request.Request(url, headers={"User-Agent": "gcu-mcp/1.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.load(r)

    try:
        g = _get("https://geocoding-api.open-meteo.com/v1/search?name="
                 + urllib.parse.quote(city) + "&count=1&language=ru")
        if not g.get("results"):
            return f"Город «{city}» не найден."
        loc = g["results"][0]
        lat, lon, nm = loc["latitude"], loc["longitude"], loc.get("name", city)
        w = _get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                 "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
                 "wind_speed_10m,weather_code")
        c = w["current"]
        desc = WMO.get(c.get("weather_code"), "")
        return (f"Погода в г. {nm}: {desc}, {round(c['temperature_2m'])}°C "
                f"(ощущается как {round(c['apparent_temperature'])}°C). "
                f"Ветер {round(c['wind_speed_10m'])} м/с, влажность {c['relative_humidity_2m']}%.")
    except Exception as e:
        return f"Не удалось получить погоду для «{city}»: {str(e)[:120]}"


# ---------------------------------------------------------------------------
# Knowledge base (RAG over the railway literature) — on-demand tool
# ---------------------------------------------------------------------------
# Embedder must MATCH what embed_kb.py used. e5-large-INSTRUCT: query is wrapped
# with an instruction; passages were embedded bare (verified best-margin).
KB_EMBED_URL = os.environ.get("KB_EMBED_URL", "http://host.docker.internal:1234/v1/embeddings")
KB_EMBED_MODEL = os.environ.get("KB_EMBED_MODEL", "text-embedding-multilingual-e5-large-instruct")
KB_QUERY_INSTRUCT = ("Instruct: Given a question, retrieve passages that answer it\nQuery: ")


def _embed_query(text):
    import json as _json
    import urllib.request as _u
    payload = {"model": KB_EMBED_MODEL, "input": [KB_QUERY_INSTRUCT + text]}
    req = _u.Request(KB_EMBED_URL, data=_json.dumps(payload).encode("utf-8"),
                     headers={"Content-Type": "application/json"})
    with _u.urlopen(req, timeout=60) as r:
        d = _json.load(r)
    return d["data"][0]["embedding"]


# Per-chunk character cap on returned passages, BY COLLECTION. Bulky textbook
# sections are trimmed hard (context-lean); short authoritative reference/glossary
# docs come back whole/generous so «перечисли всё» questions get complete lists.
KB_CAPS = {
    "reference": 4000,   # curated справки — short, return whole
    "glossary": 2500,    # org-unit blocks — keep the role→code list intact
    "pte": 2600,         # regulations — fairly complete clause text
    "textbooks": 600,    # bulky prose — trim hard (this is where bloat lives)
}
KB_CAP_DEFAULT = int(os.environ.get("KB_SNIPPET_CHARS", "800"))


@mcp.tool()
def search_knowledge(query: str, k: int = 3, collection: str = "") -> str:
    """Поиск по справочной литературе РЖД (ПТЭ, учебники, справочники).
    Возвращает релевантные фрагменты с указанием источника.

    :param query: запрос на русском
    :param k: сколько фрагментов (1–6, по умолчанию 3)
    :param collection: '' — все коллекции; 'pte' | 'textbooks' | 'reference' | 'glossary' — фильтр
    :return: фрагменты с источниками
    """
    import psycopg

    k = max(1, min(int(k), 6))
    try:
        vec = "[" + ",".join(f"{x:.7g}" for x in _embed_query(query)) + "]"
    except Exception as e:
        return f"Ошибка эмбеддинга запроса (модель {KB_EMBED_MODEL} не отвечает?): {str(e)[:160]}"

    coll = collection.strip().lower()
    coll_filter = ("AND collection = %(coll)s"
                   if coll in ("pte", "textbooks", "reference", "glossary") else "")

    # Hybrid retrieval via Reciprocal Rank Fusion (vector rank + russian FTS rank),
    # plus a small BOOST for curated 'reference' docs so authoritative справки
    # surface above general textbook chunks. Validated to route precisely.
    sql = f"""
    WITH v AS (
      SELECT id, row_number() OVER (ORDER BY embedding <=> %(vec)s::vector) AS vr
      FROM kb_chunks WHERE true {coll_filter}
      ORDER BY embedding <=> %(vec)s::vector LIMIT 30
    ),
    k AS (
      SELECT id, row_number() OVER (ORDER BY ts_rank(tsv, plainto_tsquery('russian', %(q)s)) DESC) AS kr
      FROM kb_chunks
      WHERE tsv @@ plainto_tsquery('russian', %(q)s) {coll_filter}
      LIMIT 30
    )
    SELECT c.citation, c.collection, c.is_verbatim, c.content,
           (coalesce(1.0/(60+v.vr),0) + coalesce(1.0/(60+k.kr),0)
            + CASE WHEN c.collection IN ('reference','glossary') THEN 0.010 ELSE 0 END) AS rrf
    FROM kb_chunks c
    LEFT JOIN v ON c.id = v.id
    LEFT JOIN k ON c.id = k.id
    WHERE (v.id IS NOT NULL OR k.id IS NOT NULL) {coll_filter}
    ORDER BY rrf DESC
    LIMIT %(k)s
    """
    try:
        with psycopg.connect(DB_URL, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"vec": vec, "q": query, "k": k, "coll": coll})
                rows = cur.fetchall()
    except Exception as e:
        return f"Ошибка поиска по базе знаний: {str(e)[:200]}"

    if not rows:
        return ("По справочной литературе ничего не найдено по этому запросу. "
                "Переформулируй запрос ключевыми терминами или ответь, что в "
                "доступных источниках сведений нет.")

    tags = {"pte": "НОРМАТИВ (дословно)", "reference": "СПРАВКА (курируемая)",
            "glossary": "СПРАВОЧНИК сокращений/структуры"}
    out = [f"Найдено фрагментов: {len(rows)} (источник указывай в ответе)\n"]
    for citation, coll_, verbatim, content, _rrf in rows:
        tag = tags.get(coll_, "учебник")
        cap = KB_CAPS.get(coll_, KB_CAP_DEFAULT)
        body = " ".join(content.split())               # fold internal whitespace
        if len(body) > cap:
            body = body[:cap].rsplit(" ", 1)[0] + "… [фрагмент усечён; уточни запрос для полного текста]"
        out.append(f"━━ Источник: {citation}  [{tag}]")
        out.append(body)
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# gcu_dashboard — генерация оперативного дашборда ЦГЦУ
# ---------------------------------------------------------------------------
# Builds a self-contained static HTML file with embedded data and Chart.js
# charts. No server needed — the file opens directly in any browser on
# Windows (file://). Returns the filesystem path.
# ---------------------------------------------------------------------------
@mcp.tool()
def gcu_dashboard(period: str = "апрель 2026") -> str:
    """Генерирует статический HTML-дашборд ЦГЦУ по отчётам за апрель 2026.

    Создаёт самодостаточный HTML-файл с графиками (Chart.js), таблицами
    и сводными карточками в директории ~/Desktop/ЦГЦУ отчеты/index.html.
    Файл открывается напрямую в браузере — сервер не требуется.

    Используй один раз за сессию. Если дашборд уже собран — скажи
    пользователю, что файл готов, и верни путь.

    :param period: период отчёта (по умолчанию «апрель 2026»)
    :return: полный путь к index.html
    """
    try:
        from gcu.dashboard import build
    except ImportError:
        import dashboard as _db
        return _db.build()
    return build()


if __name__ == "__main__":
    import uvicorn
    print("Starting GCU MCP server on http://0.0.0.0:8808/mcp (Streamable HTTP)")
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=8808)
