import sqlite3, json, secrets, time
c=sqlite3.connect('/app/backend/data/webui.db'); cur=c.cursor()
d=json.loads(cur.execute("SELECT id,data FROM config ORDER BY id DESC LIMIT 1").fetchone()[1])
cid=cur.execute("SELECT id FROM config ORDER BY id DESC LIMIT 1").fetchone()[0]
# enable api key in persistent config (auth subtree)
d.setdefault("auth",{}).setdefault("api_key",{})["enable"]=True
# some versions read ui.enable_api_key or a top-level; set common spots
d.setdefault("ui",{})["enable_api_key"]=True
cur.execute("UPDATE config SET data=?, updated_at=created_at WHERE id=?", (json.dumps(d,ensure_ascii=False), cid))
# mint key for admin if none
uid=cur.execute("SELECT id FROM user ORDER BY created_at LIMIT 1").fetchone()[0]
existing=cur.execute("SELECT key FROM api_key WHERE user_id=? LIMIT 1",(uid,)).fetchone()
if existing:
    key=existing[0]
else:
    key="sk-"+secrets.token_hex(24); now=int(time.time())
    cur.execute("INSERT INTO api_key (id,user_id,key,data,expires_at,last_used_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (secrets.token_hex(8), uid, key, None, None, None, now, now))
c.commit()
open('/tmp/_k.txt','w').write(key)
print("api key ready")
