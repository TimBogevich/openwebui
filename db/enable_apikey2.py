import sqlite3, json
c=sqlite3.connect('/app/backend/data/webui.db'); cur=c.cursor()
cid,data=cur.execute("SELECT id,data FROM config ORDER BY id DESC LIMIT 1").fetchone()
d=json.loads(data)
d.setdefault("auth",{})["enable_api_keys"]=True   # correct PersistentConfig path
# clean up my earlier wrong keys
d.get("auth",{}).pop("api_key",None)
d.get("ui",{}).pop("enable_api_key",None)
cur.execute("UPDATE config SET data=?, updated_at=created_at WHERE id=?", (json.dumps(d,ensure_ascii=False), cid))
c.commit()
print("auth.enable_api_keys =", d["auth"]["enable_api_keys"])
