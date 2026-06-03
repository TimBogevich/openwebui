# -*- coding: utf-8 -*-
"""
title: GCU Report Data Filter
author: gcu-team
version: 0.1.0
description: Автоматически подгружает данные из gtsu_search при вопросах о докладах ГЦУ.
type: filter
"""

import os
import re
from typing import Optional


class Filter:
    """
    Inlet filter: detects questions about GCU report data and automatically
    queries the local PostgreSQL gtsu_search table, injecting the results into
    the conversation context so the model answers from real data — without
    needing the model to "call" a tool (which LM Studio doesn't support).
    """

    def __init__(self):
        self.db_url = os.environ.get(
            "GCU_DATABASE_URL",
            "postgresql://postgres:Gcu2026!@127.0.0.1:5432/postgres"
        )
        # Keywords that trigger a DB lookup
        self.triggers = [
            "красн", "жёлт", "желт", "зон", "показател", "доклад",
            "погрузк", "грузооборот", "электровоз", "тепловоз",
            "ЦФТО", "ЦД", "ЦТ", "ЦИТ", "ЦФ", "EBITDA", "прибыль",
            "отклонен", "план", "факт", "сутки", "месяц",
            "инвест", "доставк", "срок", "подразделен",
            "color_marker", "gtsu", "report_date",
            "таблиц", "колонк", "схем", "бд", "база", "столбц", "поле", "структур",
        ]

    def _is_data_question(self, text: str) -> bool:
        low = text.lower()
        return any(t.lower() in low for t in self.triggers)

    def _build_query(self, text: str) -> str:
        """Build a relevant SQL query based on the user's question."""
        low = text.lower()

        # Determine the date (default to latest)
        date_clause = "report_date = (SELECT max(report_date) FROM gtsu_search)"
        date_match = re.search(r"(\d{1,2})\s*(марта|апреля|мая|января|февраля)", low)
        if date_match:
            day = int(date_match.group(1))
            months = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5}
            month = months.get(date_match.group(2), 3)
            date_clause = f"report_date = '2022-{month:02d}-{day:02d}'"

        # Red zone query
        if "красн" in low or "color_marker" in low:
            return f"""SELECT report_date, indicator, responsible,
                       round((metrics->>'сутки_к_плану')::numeric*100, 2) as откл_к_плану,
                       text_comment
                FROM gtsu_search
                WHERE {date_clause} AND color_marker = 2
                ORDER BY (metrics->>'сутки_к_плану')::numeric ASC
                LIMIT 15"""

        # Yellow zone
        if "жёлт" in low or "желт" in low:
            return f"""SELECT report_date, indicator, responsible,
                       round((metrics->>'сутки_к_плану')::numeric*100, 2) as откл_к_плану
                FROM gtsu_search
                WHERE {date_clause} AND color_marker = 1
                ORDER BY (metrics->>'сутки_к_плану')::numeric ASC
                LIMIT 15"""

        # By department
        dept_match = re.search(r"(ЦФТО|ЦД|ЦТ|ЦИТ|ЦФ|ЦЛ|ЦУКС)", text)
        if dept_match:
            dept = dept_match.group(1)
            return f"""SELECT report_date, indicator, color_marker,
                       round((metrics->>'сутки_к_плану')::numeric*100, 2) as откл,
                       text_comment
                FROM gtsu_search
                WHERE {date_clause} AND responsible = '{dept}'
                ORDER BY color_marker DESC, откл ASC
                LIMIT 15"""

        # General overview
        return f"""SELECT report_date, indicator, responsible, color_marker,
                   round((metrics->>'сутки_к_плану')::numeric*100, 2) as откл_к_плану
            FROM gtsu_search
            WHERE {date_clause} AND color_marker IN (1,2)
            ORDER BY color_marker DESC, откл_к_плану ASC
            LIMIT 20"""

    def _run_query(self, sql: str) -> str:
        """Execute SQL and return formatted text result."""
        try:
            import psycopg
            conn = psycopg.connect(self.db_url, connect_timeout=8)
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    if not cur.description:
                        return ""
                    cols = [d.name for d in cur.description]
                    rows = cur.fetchall()
                    if not rows:
                        return "Запрос выполнен, данных по указанным критериям не найдено."
                    lines = [" | ".join(cols)]
                    lines.append("-" * 60)
                    for row in rows:
                        lines.append(" | ".join(str(v) if v is not None else "-" for v in row))
                    return "\n".join(lines)
        except Exception as e:
            return f"Ошибка запроса к БД: {e}"

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        # Skip injection for models that use native tool calling (MCP) — they fetch
        # data themselves via the `query` tool and don't need (and are actively
        # derailed by) the filter pre-injecting its canned, often-wrong overview.
        # This covers BOTH remote- presets AND any model whose request already
        # carries tools / native function_calling (e.g. the local LM Studio 9B
        # now bound to the MCP tool with function_calling=native).
        if body.get("model", "").startswith("remote-"):
            return body
        if body.get("tools") or body.get("tool_ids"):
            return body
        params = body.get("params") or {}
        if params.get("function_calling") == "native" or body.get("function_calling") == "native":
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        last_msg = messages[-1]
        if last_msg.get("role") != "user":
            return body

        # Get the user's text
        content = last_msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))

        if not self._is_data_question(content):
            return body

        # Build and run the query
        sql = self._build_query(content)
        result = self._run_query(sql)

        if not result or "Ошибка" in result:
            return body

        # Inject the DB result as a system message right before the user message
        data_msg = {
            "role": "system",
            "content": f"""ДАННЫЕ ИЗ БАЗЫ ДОКЛАДОВ ГЦУ (результат автоматического запроса):

SQL: {sql}

Результат:
{result}

ВАЖНО: Отвечай ТОЛЬКО на основе этих данных. Переведи отклонения в проценты. Укажи показатель, подразделение и значение."""
        }

        # Insert before the last user message
        messages.insert(-1, data_msg)
        body["messages"] = messages
        return body
