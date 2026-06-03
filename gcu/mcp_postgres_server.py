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


@mcp.tool()
def query(sql: str) -> str:
    """
    Выполняет read-only SQL-запрос к таблице gtsu_search (ежедневные доклады ГЦУ РЖД).

    Колонки gtsu_search:
    - report_date (date) — дата доклада. В базе март 2022: 2022-03-01 .. 2022-03-31.
    - item_number (text) — номер показателя с иерархией ("1", "1.1", "1.1.7"); item_depth — глубина.
    - parent_path (text) — путь по иерархии родительских разделов (через " > ").
    - indicator (text) — НАЗВАНИЕ ИМЕННО ЭТОЙ строки (лист дерева).
    - full_indicator (text) — parent_path + " > " + indicator (полное название с контекстом).
    - unit, responsible (ответственное подразделение: ЦД, ЦТ, ЦФТО...), color_marker (2=красная, 1=жёлтая, 0=зелёная).
    - metrics (jsonb): факт_сутки, сутки_к_плану, сутки_к_2021, факт_месяц, месяц_к_плану,
      месяц_к_2021, факт_год, год_к_плану, год_к_2021 (для разд. III — инвест-ключи).
    - text_comment, management_actions, narrative, section_code, sheet_name, source_row.

    ВАЖНО — поиск по теме показателя:
      Данные ИЕРАРХИЧНЫ. У строк-листьев тема/категория лежит в parent_path, а в indicator —
      только короткое имя листа. ПРИМЕР: разбивка скорости доставки по дорогам хранится так:
        item_number='1.1.7', indicator='Юго-Восточная',
        parent_path='... > 1. СРЕДНЯЯ СКОРОСТЬ ДОСТАВКИ ГРУЗОВЫХ ОТПРАВОК ...'
      Поэтому `indicator ILIKE '%скорость доставки%'` НЕ найдёт строки дорог (вернёт только
      агрегат-заглушку, часто нулевую). Чтобы искать по теме, используйте full_indicator:
        WHERE full_indicator ILIKE '%скорость доставки%'      -- найдёт и категорию, и все листья
      или ищите дорогу прямо по indicator: WHERE indicator ILIKE '%Юго-Восточная%'.
      Если кажется, что «данных нет» — сначала повторите поиск по full_indicator/parent_path,
      прежде чем сделать вывод об отсутствии данных или разбивки по дорогам.

    Отклонения «к плану»/«к 2021» в metrics хранятся как доли: -0.0979 = -9.79%.
    Для красной зоны: WHERE color_marker = 2.
    Всегда добавляйте LIMIT.

    :param sql: SQL SELECT-запрос (только чтение, с LIMIT)
    :return: результат в текстовом виде
    """
    import psycopg

    clean = sql.strip().rstrip(";")
    if not clean.upper().startswith("SELECT"):
        return "Ошибка: разрешены только SELECT-запросы."
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT"]
    for word in forbidden:
        if word in clean.upper().split():
            return f"Ошибка: запрещена операция {word}."

    try:
        with psycopg.connect(DB_URL, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(clean)
                if not cur.description:
                    return "Запрос выполнен (без результата)."
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
                if not rows:
                    return "Запрос выполнен, данных не найдено."
                lines = [" | ".join(cols)]
                lines.append("-" * min(80, len(lines[0])))
                for row in rows[:50]:
                    lines.append(" | ".join(str(v) if v is not None else "-" for v in row))
                if len(rows) > 50:
                    lines.append(f"... (всего {len(rows)} строк, показано 50)")
                return "\n".join(lines)
    except Exception as e:
        return f"Ошибка: {e}"


if __name__ == "__main__":
    import uvicorn
    print("Starting GCU MCP server on http://0.0.0.0:8808/mcp (Streamable HTTP)")
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=8808)
