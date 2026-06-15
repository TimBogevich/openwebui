# -*- coding: utf-8 -*-
"""NEUTRAL system-prompt block addressing the 14.06.2026 РЖД-analyst feedback.
Pure declarative facts — no imperatives («бери/называй») and no prohibitions
(«не складывай/только»). A small model reads them as context, not as commands to
comply with or resist. Idempotent via the marker; appended LAST.
Run inside the OWI container:
  docker exec -i gcu-openwebui python3 < db/fix_analyst_feedback.py
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
MARK = "<!-- analyst-fix-2026-06 -->"

BLOCK = (
    MARK + "\n"
    "Дороги и станции приводятся перечнем со значениями, формулировки нейтральные («наблюдается», «динамика следующая», «зона риска»). "
    "Мониторинг оперативных показателей ЦГЦУ — ежесуточный. "
    "Развёрнутый разбор, рекомендации и мероприятия — отдельный ответ по прямому запросу."
)

c = sqlite3.connect(DB); cur = c.cursor(); now = int(time.time())
for mid, params in cur.execute("SELECT id,params FROM model WHERE is_active=1").fetchall():
    p = json.loads(params) if params else {}
    s = p.get("system", "")
    if MARK in s:
        # idempotent refresh: cut the old block off and re-append the current text
        s = s[:s.find(MARK)].rstrip()
    s = s.rstrip() + "\n\n" + BLOCK
    p["system"] = s
    cur.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                (json.dumps(p, ensure_ascii=False), now, mid))
    print(f"  {mid}: analyst-fix block set")
c.commit(); c.close(); print("done")
