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
                    # Two facts that save the model from blind fishing:
                    #  (a) which report dates actually exist (so it stops guessing dates)
                    #  (b) names are abbreviated → use trigram fuzzy search, not ILIKE-by-word
                    try:
                        cur.execute(
                            "SELECT min(report_date), max(report_date), count(*) FROM reports")
                        dmin, dmax, ndays = cur.fetchone()
                        out.append("")
                        out.append(f"Доступные даты докладов (reports.report_date): {dmin} .. {dmax} "
                                   f"(всего {ndays}). Перед запросом за период убедись, что дата есть.")
                        out.append("Названия показателей (metrics.name) СОКРАЩЕНЫ в источнике "
                                   "(«груз.», «в т.ч.», «установл.», «собл.»). Поиск по точному слову "
                                   "через ILIKE часто промахивается. Ищи по СМЫСЛУ через триграммное "
                                   "сходство: WHERE name % 'твой запрос'  или  "
                                   "ORDER BY similarity(name, 'твой запрос') DESC LIMIT 5.")

                        # FIX 2: warn about columns that DON'T exist (models hallucinate these)
                        try:
                            cur.execute(
                                "SELECT column_name FROM information_schema.columns "
                                "WHERE table_name='metrics' ORDER BY ordinal_position")
                            real_cols = {r[0] for r in cur.fetchall()}
                            ghost = [c for c in ("value","plan","fact","report_date","road_name",
                                                  "year","month","date","delta","status")
                                     if c not in real_cols]
                            if ghost:
                                out.append(f"НЕТ таких колонок в metrics: {', '.join(ghost)}. "
                                           f"Числовые данные: day_fact, month_fact, year_fact, "
                                           f"day_to_plan, month_to_plan, day_to_prev_year, month_to_prev_yr.")
                        except Exception:
                            conn.rollback()

                        # FIX 3: category→section navigation map (dynamic from DB)
                        # Tells the model WHERE each topic lives without hardcoding names.
                        try:
                            cur.execute(
                                "SELECT DISTINCT section_roman, category "
                                "FROM metrics WHERE category IS NOT NULL AND section_roman IS NOT NULL "
                                "ORDER BY section_roman, category")
                            cat_rows = cur.fetchall()
                            if cat_rows:
                                out.append("")
                                out.append("НАВИГАЦИЯ по разделам (section_roman → category):")
                                cur_sec = None
                                for sec, cat in cat_rows:
                                    if sec != cur_sec:
                                        out.append(f"  Раздел {sec}:")
                                        cur_sec = sec
                                    out.append(f"    • {cat[:70]}")
                        except Exception:
                            conn.rollback()

                        # FIX 4: warn that indicator_number is NOT unique
                        try:
                            cur.execute(
                                "SELECT count(*) FROM ("
                                "  SELECT indicator_number FROM metrics "
                                "  GROUP BY indicator_number HAVING count(DISTINCT name)>1"
                                ") sub")
                            ambig = cur.fetchone()[0]
                            if ambig:
                                out.append(f"")
                                out.append(f"⚠ indicator_number НЕ уникален: {ambig} номеров "
                                           f"соответствуют >1 показателю (разные листы/разделы). "
                                           f"ВСЕГДА фильтруй по name, не только по indicator_number.")
                        except Exception:
                            conn.rollback()

                        out.append("")
                        out.append("СПРАВКИ-ИСТОЧНИКИ (детализация к докладу ГЦУ) — связаны с reports по report_date:")
                        out.append("  • spravki_delays       — задержанные поезда по кодам причин и дорогам "
                                   "(коды 0,1,2,4,5,6,21,22,24,43,44,92; поля: delay_code, delay_name, road_code, trains, wagons). "
                                   "Используй для вопросов о задержках по кодам/дорогам.")
                        out.append("  • spravki_failures     — отказы техсредств 1-2 кат. по подразделениям "
                                   "(поля: dept, failures_2025, failures_2026, change_pct, resolved). "
                                   "Используй для вопросов об отказах техсредств по подразделениям.")
                        out.append("  • spravki_locomotives  — эксплуатируемый парк локомотивов "
                                   "(поля: section, polygon, road, plan, fact, delta). "
                                   "Используй для вопросов о локомотивном парке.")
                        out.append("  • spravki_port_stations— работа припортовых станций ДВС/ОКТ/СКАВ "
                                   "(поля: road, station, load_plan, load_fact, detained_trains, wagons_total). "
                                   "Используй для вопросов о портах и отставленных поездах на припортовых станциях.")
                        out.append("  • spravki_speed        — участковая и техническая скорость по дорогам "
                                   "(поля: speed_type ['section'|'technical'], road, norm, day_fact, day_delta, month_fact). "
                                   "Используй для вопросов о скорости по дорогам.")
                        out.append("  Даты покрытия справок: "
                                   "SELECT DISTINCT report_date FROM spravki_delays ORDER BY report_date")
                    except Exception:
                        conn.rollback()
                out.append("")
                out.append("КОЛОНКИ (тип — комментарий):")
                for name, dtype, comment in cols:
                    out.append(f"  • {name} ({dtype})" + (f" — {comment}" if comment else ""))

                # 2) per-column profile: ranges, low-cardinality value lists, sample values
                out.append("")
                out.append("ОБРАЗЦЫ ДАННЫХ (из реальных строк, для понимания соглашений хранения):")
                for name, dtype, _ in cols:
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
    # Anti-loop guard: catch the same SELECT being re-run instead of answering.
    level, prior = _qguard_check(sql)
    if level == 2:
        return ("⛔ СТОП: этот запрос уже выполнялся "
                f"{prior + 1} раз(а) с тем же результатом. Данные не изменятся. "
                "НЕ повторяй запрос — сформулируй ОТВЕТ на основе уже полученных "
                "данных. Если данных действительно не хватает, честно скажи, "
                "каких именно, и не зацикливайся.")

    result, err = _run_select(sql)
    if err:
        return err
    cols, rows = result
    out = _fmt_table(cols, rows)
    if level == 1:
        out = ("⚠️ Внимание: ты уже выполнял ЭТОТ ЖЕ запрос — результат тот же. "
               "Переходи к ОТВЕТУ или измени запрос, не повторяй его снова.\n\n" + out)
    return out


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


if __name__ == "__main__":
    import uvicorn
    print("Starting GCU MCP server on http://0.0.0.0:8808/mcp (Streamable HTTP)")
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=8808)
