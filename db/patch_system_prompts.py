# -*- coding: utf-8 -*-
"""
Idempotently append S4 semantic blocks (A8 period/accumulation + A1 hierarchy)
to all active model system prompts in the container OWI DB.
Run inside the container: python3 /app/backend/data/patch_system_prompts.py
"""
import sqlite3, json, sys

DB = '/app/backend/data/webui.db'

A8_BLOCK = """
ПЕРИОД И НАКОПЛЕНИЕ
факт_месяц и факт_год — нарастающим итогом с начала месяца/года, это НЕ дневные значения.
На вопрос про сутки используй ТОЛЬКО факт_сутки.
НИКОГДА не подставляй год/месяц вместо суток и не сравнивай накопительный итог с суточным планом.
В ответе всегда указывай период (за сутки / с начала месяца / с начала года)."""

A1_BLOCK = """
ИЕРАРХИЯ И РАЗРЕЗЫ ПО ДОРОГАМ
Детализация по дорогам/филиалам («в т.ч.») — это дочерние строки дерева:
indicator = название дороги (Октябрьская, Куйбышевская…), тема/раздел — в parent_path/full_indicator.
Чтобы найти разбивку по дорогам, ищи по full_indicator (не indicator):
  WHERE full_indicator ILIKE '%скорость доставки%'
Если indicator ILIKE вернул 0 строк — повтори поиск через full_indicator/parent_path прежде чем делать вывод об отсутствии разбивки."""

SENTINEL_A8 = 'факт_месяц и факт_год — нарастающим итогом'
SENTINEL_A1 = 'Детализация по дорогам/филиалам'

db = sqlite3.connect(DB)
models = db.execute("SELECT id, params FROM model WHERE is_active=1").fetchall()
updated = 0
for mid, raw_params in models:
    p = json.loads(raw_params) if raw_params else {}
    sys = p.get('system', '')
    if not sys:
        continue
    changed = False
    if SENTINEL_A8 not in sys:
        sys += A8_BLOCK
        changed = True
    if SENTINEL_A1 not in sys:
        sys += A1_BLOCK
        changed = True
    if changed:
        p['system'] = sys
        db.execute("UPDATE model SET params=? WHERE id=?", (json.dumps(p, ensure_ascii=False), mid))
        print(f"patched: {mid}")
        updated += 1
    else:
        print(f"skip (already has blocks): {mid}")
db.commit()
print(f"done — {updated} models updated")
