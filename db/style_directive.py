# -*- coding: utf-8 -*-
"""Add a SHORT response-style directive to the active presets.

Output style only (kept minimal): name the color zone in words, keep DB
table/column identifiers out of the answer, cite the source by its official
system name, use full road names.

NOTE (15.06.2026): the old «образец доклада» auto-trigger was REMOVED. It mapped
«проанализируй / причины / конкретные цифры» onto a full report template (выводы +
решения) — the over-analyzing behavior the РЖД client rejected. The assistant now
reports facts; развёрнутый разбор/рекомендации only on explicit request (see the
<!-- analyst-fix-2026-06 --> block).

Idempotent: re-running replaces the block by its marker. Run inside container:
  docker exec -i gcu-openwebui python3 < db/style_directive.py
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
MARKER = "<!-- style-directive -->"

BLOCK = (
    f"\n\n{MARKER}\n"
    "СТИЛЬ ОТВЕТА: цветовая зона словом — «красная зона», «жёлтая зона», «зелёная зона». "
    "Ответ на русском, человеческим языком: внутренние имена таблиц и колонок базы не выводятся. "
    "Источник — официальное название системы из строки «ИСТОЧНИК ДЛЯ ОТВЕТА» в describe "
    "(КАСАНТ, АРМ ОНД, СИС Эффект, ПК ИУС ЦУП НП, ЕМД ПП УР, АСУ ВОП-2, Доклад СКИМ ОД). "
    "Дороги — полным именем."
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
