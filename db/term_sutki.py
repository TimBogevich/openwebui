# -*- coding: utf-8 -*-
"""Терминологическая директива: day_fact = факт ЗА СУТКИ (не «за день»).

Чисто промптовое правило, без хардкода в схеме/describe. Универсальная
конвенция этой витрины: суточный показатель доклада ЦГЦУ — это значение за
прошедшие отчётные сутки. Модель должна и понимать вопрос «за сутки», и
называть значение в ответе «за сутки», а не «за день».

Идемпотентно: применяется ко ВСЕМ активным пресетам, повторный запуск
заменяет блок, не дублирует.

Запуск внутри контейнера:
  docker exec -i gcu-openwebui python3 < db/term_sutki.py
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
MARKER = "<!-- term-sutki -->"

BLOCK = (
    f"\n\n{MARKER}\n"
    "day_fact — факт за сутки; в ответах пиши «за сутки», не «за день». "
    "month_fact/year_fact — нарастающий итог, не суточные."
)


def upsert(prompt: str) -> str:
    if MARKER in prompt:
        prompt = prompt.split(MARKER)[0].rstrip()
    return prompt.rstrip() + BLOCK


db = sqlite3.connect(DB)
now = int(time.time())
updated = 0
for mid, raw in db.execute("SELECT id, params FROM model WHERE is_active=1").fetchall():
    p = json.loads(raw) if raw else {}
    s = p.get("system", "")
    if not s:
        print(f"skip (no system prompt): {mid}")
        continue
    p["system"] = upsert(s)
    db.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
               (json.dumps(p, ensure_ascii=False), now, mid))
    print(f"patched: {mid}  (sys_len -> {len(p['system'])})")
    updated += 1
db.commit()
print(f"done — {updated} active model(s) updated")
db.close()
