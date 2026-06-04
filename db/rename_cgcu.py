# -*- coding: utf-8 -*-
"""Replace the abbreviation ГЦУ -> ЦГЦУ in model NAMES and system prompts.
Idempotent: 'ЦГЦУ' contains 'ГЦУ' as a substring, so skip any text that already
contains 'ЦГЦУ' (already converted) to avoid producing 'ЦЦГЦУ'."""
import sqlite3, json, time
DB="/app/backend/data/webui.db"
c=sqlite3.connect(DB); cur=c.cursor(); now=int(time.time())

def conv(text):
    if not text: return text
    if "ЦГЦУ" in text:        # already converted -> leave as-is
        return text
    return text.replace("ГЦУ", "ЦГЦУ")

for r in cur.execute("SELECT id,name,params FROM model WHERE is_active=1").fetchall():
    mid, name, params = r
    p = json.loads(params) if params else {}
    new_name = conv(name)
    sysp = p.get("system","")
    new_sys = conv(sysp)
    p["system"] = new_sys
    cur.execute("UPDATE model SET name=?, params=?, updated_at=? WHERE id=?",
                (new_name, json.dumps(p, ensure_ascii=False), now, mid))
    print(f"  {mid}")
    print(f"     name: {name!r} -> {new_name!r}")
    print(f"     sys[:60]: {new_sys[:60]!r}")
c.commit(); c.close()
print("done")
