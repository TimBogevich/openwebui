"""
title: GCU Database Query
author: gcu-team
version: 0.1.0
description: Выполняет SQL-запрос к таблице gtsu_search (ежедневные доклады ГЦУ РЖД) и возвращает результат.
"""

import os
import json
from typing import Any


class Tools:
    def __init__(self):
        self.db_url = os.environ.get(
            "GCU_DATABASE_URL",
            "postgresql://postgres:CHANGEME@127.0.0.1:5432/postgres"
        )

    def query_gcu_report(self, sql: str, __user__: dict = {}) -> str:
        """
        Выполняет SQL-запрос к таблице gtsu_search с данными ежедневных докладов ГЦУ РЖД.
        Таблица содержит: report_date, indicator, unit, responsible, color_marker (2=красная зона),
        metrics (jsonb: факт_сутки, сутки_к_плану, факт_месяц...), text_comment, management_actions, narrative.
        Разрешены только SELECT-запросы с LIMIT.

        :param sql: SQL SELECT-запрос к gtsu_search (только чтение, обязательно с LIMIT)
        :return: результат запроса в текстовом виде
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
            with psycopg.connect(self.db_url, connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(clean)
                    cols = [d.name for d in cur.description] if cur.description else []
                    rows = cur.fetchall()
                    if not rows:
                        return "Запрос выполнен, но результат пустой."
                    lines = [" | ".join(cols)]
                    lines.append("-" * len(lines[0]))
                    for row in rows[:50]:
                        lines.append(" | ".join(str(v) for v in row))
                    if len(rows) > 50:
                        lines.append(f"... ({len(rows)} строк всего, показано 50)")
                    return "\n".join(lines)
        except Exception as e:
            return f"Ошибка выполнения: {e}"
