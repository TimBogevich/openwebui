# -*- coding: utf-8 -*-
"""
GCU Postgres MCP Server — Streamable HTTP transport.

A minimal MCP server that exposes a `query` tool for read-only SQL against the
local gtsu_search table. Speaks the Streamable HTTP protocol that Open WebUI
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
    instructions="Сервер для SQL-запросов к таблице gtsu_search (доклады ГЦУ РЖД)",
)

DB_URL = os.environ.get(
    "GCU_DATABASE_URL",
    "postgresql://postgres:Gcu2026!@127.0.0.1:5432/postgres"
)


DEFAULT_TABLE = os.environ.get("GCU_TABLE", "gtsu_search")

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


@mcp.tool()
def describe(table: str = "") -> str:
    """
    Возвращает АКТУАЛЬНУЮ структуру таблицы прямо из базы (не захардкожено): список колонок
    с типами и комментариями, число строк, диапазоны дат, а также РЕАЛЬНЫЕ примеры значений
    каждой колонки и ключи JSONB-полей. Вызывайте ПЕРВЫМ, чтобы понять схему и соглашения
    хранения, и ПОВТОРНО, если запрос неожиданно вернул мало/ноль строк — прежде чем делать
    вывод об отсутствии данных. Примеры значений показывают, в какой колонке что лежит
    (например, что названия-листья дерева лежат в одной колонке, а тема/раздел — в другой).

    :param table: имя таблицы (по умолчанию основная таблица докладов)
    :return: текстовое описание схемы и образцов данных
    """
    import psycopg

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

                out = [f"Таблица: {tbl} — строк: {n_rows}"]
                if tbl_comment:
                    out.append(f"Описание: {tbl_comment}")
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
    """
    Выполняет read-only SQL-запрос (SELECT/WITH) к базе докладов ГЦУ РЖД.

    Если не знаете точную структуру или имена колонок — сначала вызовите инструмент
    `describe`: он покажет актуальную схему и реальные образцы значений прямо из базы.

    Данные иерархичны (дерево показателей). Числовые отклонения хранятся как доли
    (-0.0979 = -9.79%). Всегда добавляйте LIMIT. Если запрос вернул 0 строк — не делайте
    вывод об отсутствии данных сразу: вызовите `describe` и проверьте, в какой колонке
    лежит искомое (имя-лист и тема/раздел часто в разных колонках), затем повторите поиск.

    :param sql: SQL SELECT/WITH-запрос (только чтение, с LIMIT)
    :return: результат в текстовом виде
    """
    result, err = _run_select(sql)
    if err:
        return err
    cols, rows = result
    return _fmt_table(cols, rows)


if __name__ == "__main__":
    import uvicorn
    print("Starting GCU MCP server on http://0.0.0.0:8808/mcp (Streamable HTTP)")
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=8808)
