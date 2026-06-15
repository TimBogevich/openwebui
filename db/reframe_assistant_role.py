# -*- coding: utf-8 -*-
"""Reframe the assistant's role from «аналитик» (judge/conclude posture) to a
reporting ASSISTANT, per the 15.06.2026 РЖД client meeting: the model should
report facts/figures, not produce analytical conclusions unless explicitly asked.

Targeted literal replacements on the LIVE consolidated prompt (the role/style text
was hand-merged and no longer matches the original generator scripts verbatim, so
we patch the live value directly). Idempotent: each replacement is a no-op if the
old text is already gone. Run inside the OWI container:
  docker exec -i gcu-openwebui python3 < db/reframe_assistant_role.py
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"

# (old_substring, new_substring) — applied in order, each guarded by membership.
REPLACEMENTS = [
    # top style line: drop «и аналитический», soften «как аналитик»
    ("СТИЛЬ ОБЩЕНИЯ: строгий деловой и аналитический.",
     "СТИЛЬ ОБЩЕНИЯ: строгий деловой."),
    ("Пиши сухо, по существу, как аналитик для руководства ОАО «РЖД».",
     "Пиши сухо, по существу, для руководства ОАО «РЖД»."),
    ("Пиши сухо, по существу, как в официальной аналитической записке для руководства ОАО «РЖД».",
     "Пиши сухо, по существу, для руководства ОАО «РЖД»."),
    # role block: «аналитический ассистент» -> «ассистент»
    ("Ты — аналитический ассистент по ежедневным докладам ЦГЦУ",
     "Ты — ассистент по ежедневным докладам ЦГЦУ"),
    ("Ты — аналитический ассистент по ежедневным докладам ГЦУ",
     "Ты — ассистент по ежедневным докладам ГЦУ"),
]

db = sqlite3.connect(DB); now = int(time.time()); n = 0
for mid, raw in db.execute("SELECT id, params FROM model WHERE is_active=1").fetchall():
    p = json.loads(raw) if raw else {}
    s = p.get("system", "")
    if not s:
        continue
    orig = s
    for old, new in REPLACEMENTS:
        if old in s:
            s = s.replace(old, new)
    if s != orig:
        p["system"] = s
        db.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                   (json.dumps(p, ensure_ascii=False), now, mid))
        print(f"reframed: {mid}")
        n += 1
    else:
        print(f"no-op (already reframed): {mid}")
db.commit(); db.close()
print(f"done — {n} updated")
