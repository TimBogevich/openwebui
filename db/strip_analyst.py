# -*- coding: utf-8 -*-
"""Remove the 'ТЫ — АНАЛИТИК' system-prompt block from all active models.
SQL guidance moves into the query tool's description instead (contextual guide,
not a standing behavioral mandate). Idempotent."""
import sqlite3, json, time
DB="/app/backend/data/webui.db"
c=sqlite3.connect(DB); cur=c.cursor(); now=int(time.time())
for mid, params in cur.execute("SELECT id,params FROM model WHERE is_active=1").fetchall():
    p=json.loads(params) if params else {}
    s=p.get("system","")
    i=s.find("ТЫ — АНАЛИТИК")
    if i==-1:
        print(f"  {mid}: nothing to remove"); continue
    s=s[:i].rstrip()+"\n"
    p["system"]=s
    cur.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                (json.dumps(p,ensure_ascii=False), now, mid))
    print(f"  {mid}: analyst block removed")
c.commit(); c.close(); print("done")
