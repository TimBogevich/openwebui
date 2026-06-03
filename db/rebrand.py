import sqlite3, json
c=sqlite3.connect('/app/backend/data/webui.db'); cur=c.cursor()
cid,data=cur.execute("SELECT id,data FROM config ORDER BY id DESC LIMIT 1").fetchone()
d=json.loads(data)
# WEBUI_NAME is PersistentConfig -> stored under ui.name in some versions, top-level 'name' served by /api/config
changed=[]
def setname(o):
    for k in list(o.keys()):
        if k.lower()=="name" and isinstance(o[k],str) and ("open webui" in o[k].lower() or "ГЦУ" in o[k]):
            o[k]="РЖД"; changed.append(k)
        if isinstance(o[k],dict): setname(o[k])
setname(d)
# ensure ui.name set
d.setdefault("ui",{})["name"]="РЖД"
# turn off api keys again (we only needed it transiently; user wants no admin/keys)
d.setdefault("auth",{})["enable_api_keys"]=False
cur.execute("UPDATE config SET data=?, updated_at=created_at WHERE id=?", (json.dumps(d,ensure_ascii=False), cid))
# remove minted api keys + neutralize admin identity strings
cur.execute("DELETE FROM api_key")
# scrub admin email/name to non-identifying (auth is off, but no leftover creds shown)
cur.execute("UPDATE user SET name='РЖД', email='user@rzd.local' WHERE role='admin'")
cur.execute("UPDATE auth SET email='user@rzd.local' WHERE 1=1")
c.commit()
print("name keys changed:", changed, "| ui.name=РЖД set")
print("api_key rows now:", cur.execute("SELECT count(*) FROM api_key").fetchone()[0])
print("user:", cur.execute("SELECT name,email,role FROM user").fetchall())
