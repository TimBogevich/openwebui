import sqlite3, json
c=sqlite3.connect('/app/backend/data/webui.db'); cur=c.cursor()
cur.execute("UPDATE user SET profile_image_url='/static/user.png', name='РЖД Интер' WHERE role='admin'")
cid,data=cur.execute("SELECT id,data FROM config ORDER BY id DESC LIMIT 1").fetchone()
d=json.loads(data); d.setdefault("ui",{})["name"]="РЖД Интер"
cur.execute("UPDATE config SET data=?, updated_at=created_at WHERE id=?", (json.dumps(d,ensure_ascii=False), cid))
c.commit()
print("user:", cur.execute("SELECT name,profile_image_url FROM user").fetchall())
