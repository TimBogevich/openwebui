# -*- coding: utf-8 -*-
"""Add a SHORT RZD-analyst style directive to the active presets.

Two things only (kept minimal to avoid prompt bloat):
1. Cite the source (table/справка) for each data block — the single most
   recognizable RZD-analyst trait.
2. For analytical «проанализируй показатель / причины» questions, consult the
   curated report template via search_knowledge(collection='reference') — so the
   full structure (3 periods → red zone → причины → цифры по источникам →
   решения) lives in the KB on demand, NOT hard-coded in the prompt.

Idempotent: re-running replaces the block by its marker. Run inside container:
  docker exec -i gcu-openwebui python3 < db/style_directive.py
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
MARKER = "<!-- style-directive -->"

BLOCK = (
    f"\n\n{MARKER}\n"
    "СТИЛЬ ОТВЕТА (как аналитик ЦГЦУ): каждый блок данных сопровождай краткой "
    "ссылкой на источник в скобках — бери официальное название системы из строки "
    "«ИСТОЧНИК ДЛЯ ОТВЕТА» в describe таблицы (КАСАНТ, АРМ ОНД, СИС Эффект, ПК ИУС ЦУП НП, "
    "ЕМД ПП УР, АСУ ВОП-2, Доклад СКИМ ОД), а не имя таблицы БД. Дороги называй полным "
    "именем. Если показатель не достигает цели за все три периода (сутки, месяц, "
    "год) — отметь «красная зона риска». Для развёрнутого разбора показателя "
    "(«проанализируй», «причины невыполнения», «конкретные цифры») сверься с "
    "образцом доклада: search_knowledge('образец доклада показатель', collection='reference')."
)


def upsert(prompt: str) -> str:
    if MARKER in prompt:
        prompt = prompt.split(MARKER)[0].rstrip()
    return prompt.rstrip() + BLOCK


db = sqlite3.connect(DB)
now = int(time.time())
n = 0
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
    n += 1
db.commit()
print(f"done — {n} active model(s) updated")
db.close()
