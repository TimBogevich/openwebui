# -*- coding: utf-8 -*-
"""Add a SOFT data-handling hint to all active models (no rigid formulas that
the model might mechanically over-apply / hallucinate around). Idempotent."""
import sqlite3, json, time
DB="/app/backend/data/webui.db"
HINT = (
 "РАБОТА С ДАННЫМИ: значения отклонений (к плану, к прошлому году) хранятся как "
 "доли — переводи их в проценты при ответе. Не складывай и не смешивай доли с "
 "абсолютными величинами. Если точный расчёт неочевиден или не уверен — приведи "
 "сырые значения (факт и отклонение) и поясни, а не подставляй выдуманную формулу. "
 "Числа бери дословно из результата запроса."
)
MARKER = "РАБОТА С ДАННЫМИ:"
c=sqlite3.connect(DB); cur=c.cursor(); now=int(time.time())
for mid, params in cur.execute("SELECT id,params FROM model WHERE is_active=1").fetchall():
    p=json.loads(params) if params else {}
    s=p.get("system","")
    if MARKER in s:
        print(f"  {mid}: already present"); continue
    s = s.rstrip() + "\n\n" + HINT      # append at the end
    p["system"]=s
    cur.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                (json.dumps(p,ensure_ascii=False), now, mid))
    print(f"  {mid}: data hint added")
c.commit(); c.close(); print("done")
