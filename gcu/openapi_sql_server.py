# -*- coding: utf-8 -*-
"""
GCU SQL OpenAPI Tool Server
Exposes a read-only SQL query tool via OpenAPI spec.
Open WebUI registers it under Admin → Tool Servers (OpenAPI type).
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_URL = os.environ.get(
    "GCU_DATABASE_URL",
    "postgresql://postgres:CHANGEME@127.0.0.1:5432/postgres"
)

app = FastAPI(
    title="GCU SQL Tool",
    description="Read-only SQL queries against gtsu_search (ежедневные доклады ГЦУ РЖД)",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class QueryRequest(BaseModel):
    sql: str


class QueryResponse(BaseModel):
    result: str


@app.post("/query", operation_id="query_gtsu", summary="SQL query to gtsu_search")
def query(req: QueryRequest) -> QueryResponse:
    """
    Выполняет SELECT-запрос к таблице gtsu_search.

    Таблица: report_date, indicator, responsible, color_marker (2=красная, 1=жёлтая, 0=зелёная),
    metrics jsonb (факт_сутки, сутки_к_плану, сутки_к_2021, факт_месяц, месяц_к_плану…).
    Отклонения — доли: -0.0979 = -9.79%. Только SELECT с LIMIT.
    """
    import psycopg

    sql = req.sql.strip().rstrip(";")
    if not sql.upper().startswith("SELECT"):
        return QueryResponse(result="Ошибка: разрешены только SELECT-запросы.")
    for word in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT"):
        if word in sql.upper().split():
            return QueryResponse(result=f"Ошибка: запрещена операция {word}.")
    try:
        with psycopg.connect(DB_URL, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                if not cur.description:
                    return QueryResponse(result="Запрос выполнен (без результата).")
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
                if not rows:
                    return QueryResponse(result="Данных не найдено.")
                lines = [" | ".join(cols), "-" * min(80, sum(len(c) for c in cols))]
                for row in rows[:50]:
                    lines.append(" | ".join(str(v) if v is not None else "-" for v in row))
                if len(rows) > 50:
                    lines.append(f"... ({len(rows)} строк, показано 50)")
                return QueryResponse(result="\n".join(lines))
    except Exception as e:
        return QueryResponse(result=f"Ошибка: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8809)
