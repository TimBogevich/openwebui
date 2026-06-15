# -*- coding: utf-8 -*-
"""Убрать захардкоженный список таблиц из промпта — пусть состав таблиц
берётся из describe (там уже есть справки spravki_*).

Проблема: в промпте было «Доступные таблицы: reports, metrics, ...,
kb_chunks» без spravki_*, и модель верила списку, а не инструменту —
отвечала «таблицы spravki нет». describe() справки видит.

Идемпотентно: ищет строку «Доступные таблицы: ... .» и заменяет на
короткую отсылку к describe. По всем активным пресетам.

  docker exec -i gcu-openwebui python3 < db/fix_tables_line.py
"""
import sqlite3, json, re, time

DB = "/app/backend/data/webui.db"
PAT = re.compile(r"Доступные таблицы:[^\n]*")
REPL = ("Полный список таблиц и их колонки узнавай через describe — "
        "не полагайся на память о составе базы (есть и таблицы-справки).")

db = sqlite3.connect(DB)
now = int(time.time())
n = 0
for mid, raw in db.execute("SELECT id, params FROM model WHERE is_active=1").fetchall():
    p = json.loads(raw) if raw else {}
    s = p.get("system", "")
    if not s or not PAT.search(s):
        print(f"skip (no table line): {mid}")
        continue
    p["system"] = PAT.sub(REPL, s)
    db.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
               (json.dumps(p, ensure_ascii=False), now, mid))
    print(f"patched: {mid}")
    n += 1
db.commit()
print(f"done — {n} active model(s) updated")
db.close()
