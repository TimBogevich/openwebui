# -*- coding: utf-8 -*-
"""Hide the two raw ap.qwen/* base models so only the 4 named presets show.
Per OWI get_all_models(): a custom model row with base_model_id=None, same id as
a base, and is_active=0 -> removes that base from the list."""
import sqlite3, json, time
DB="/app/backend/data/webui.db"
c=sqlite3.connect(DB); cur=c.cursor()
now=int(time.time())
uid=cur.execute("SELECT id FROM user WHERE role='admin' LIMIT 1").fetchone()[0]
HIDE = ["ap.qwen/qwen3.6-27b", "ap.qwen/qwen3.5-9b"]
for mid in HIDE:
    exists=cur.execute("SELECT id FROM model WHERE id=?", (mid,)).fetchone()
    if exists:
        cur.execute("UPDATE model SET is_active=0, updated_at=? WHERE id=?", (now, mid))
    else:
        cur.execute(
            "INSERT INTO model (id,user_id,base_model_id,name,params,meta,updated_at,created_at,is_active) "
            "VALUES (?,?,?,?,?,?,?,?,0)",
            (mid, uid, None, mid, "{}", "{}", now, now))
    print("  hidden base:", mid)
c.commit()
print("done")
c.close()
