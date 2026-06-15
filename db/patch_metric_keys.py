# -*- coding: utf-8 -*-
"""
Idempotently add ONE general schema-convention block (A9) to active model
system prompts. NOT per-question logic — it's a universal rule of THIS витрина
that holds for any future data with the same tables:

  • many indicators (счётчики, накопительные) have NO факт_сутки — their value
    lives in факт_месяц / факт_год. Empty факт_сутки ≠ «данных нет».
  • разрез по подразделениям часто в колонке responsible (ЦТ/ЦД/ЦДИ…),
    а не только в indicator/дорогах.
  • не зацикливайся: сформулировал SQL — СРАЗУ вызови query, не переобдумывай.

This is exactly the «mix, not hard-coded» the user asked for: a reusable
convention the model applies itself, instead of a bespoke view per metric.

Run inside the container: python3 /app/backend/data/patch_metric_keys.py
"""
import sqlite3, json

DB = "/app/backend/data/webui.db"

A9_BLOCK = """
КЛЮЧИ ЗНАЧЕНИЙ (важно для счётчиков и количеств)
Не у каждого показателя есть суточное значение. Счётчики и итоговые показатели
(количество фактов, опозданий, задержек, штук «ед.») часто имеют ПУСТОЙ факт_сутки —
их значение лежит в факт_месяц (нарастающим итогом с начала месяца), иногда в факт_год.
Поэтому: если факт_сутки пустой/NULL — это НЕ «данных нет»; возьми факт_месяц
(или факт_год). Для вопросов «сколько всего за месяц», «количество…», «максимум по…»
сортируй и сравнивай по факт_месяц, а не по факт_сутки.
Разрез «кто/какое подразделение» часто в колонке responsible (ЦТ, ЦД, ЦДИ, ЦФТО…),
а детализация «в т.ч.» — дочерние строки (item_number вида 6.1.2.x). Максимальное
значение в разделе — дочерние строки этого раздела, сортировка по факт_месяц DESC.
Прежде чем сказать «данных нет» — проверь и факт_месяц, и факт_год, и колонку responsible.

ДЕЙСТВУЙ, НЕ ЗАЦИКЛИВАЙСЯ
Сформулировал SQL — СРАЗУ вызови query (не переобдумывай один и тот же запрос).
Достаточно 1–3 вызовов: describe (при необходимости) → query → ответ. Если запрос
вернул 0 строк — измени КЛЮЧ (факт_месяц вместо факт_сутки) или колонку, но не
повторяй тот же запрос и не рассуждай по кругу."""

SENTINEL = "КЛЮЧИ ЗНАЧЕНИЙ (важно для счётчиков"

db = sqlite3.connect(DB)
updated = 0
for mid, raw in db.execute("SELECT id, params FROM model WHERE is_active=1").fetchall():
    p = json.loads(raw) if raw else {}
    s = p.get("system", "")
    if not s or SENTINEL in s:
        print(f"skip (already has block): {mid}")
        continue
    p["system"] = s + A9_BLOCK
    db.execute("UPDATE model SET params=? WHERE id=?", (json.dumps(p, ensure_ascii=False), mid))
    print(f"patched: {mid}")
    updated += 1
db.commit()
print(f"done — {updated} models updated")
