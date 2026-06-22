import sqlite3, json, time
DB="/app/backend/data/webui.db"
content=open("/tmp/pp.py",encoding="utf-8").read()
c=sqlite3.connect(DB); cur=c.cursor()
# admin user id (owner of existing function)
uid=cur.execute("SELECT user_id FROM function WHERE id='gcu_report_filter'").fetchone()
uid=uid[0] if uid else cur.execute("SELECT id FROM user LIMIT 1").fetchone()[0]
now=int(time.time())
meta=json.dumps({"description":"Детерминированная нормализация единиц/типографики в финальном ответе","manifest":{}})
valves=json.dumps({})
fid="gcu_answer_postprocessor"
exists=cur.execute("SELECT 1 FROM function WHERE id=?", (fid,)).fetchone()
if exists:
    cur.execute("UPDATE function SET content=?, is_active=1, is_global=1, updated_at=? WHERE id=?", (content, now, fid))
    print("updated existing", fid)
else:
    cur.execute("""INSERT INTO function (id,user_id,name,type,content,meta,valves,is_active,is_global,updated_at,created_at)
                   VALUES (?,?,?,?,?,?,?,1,1,?,?)""",
                (fid, uid, "ЦГЦУ Answer Post-Processor", "filter", content, meta, valves, now, now))
    print("inserted", fid)
# deactivate the dead old filter (queries deleted gtsu_search)
cur.execute("UPDATE function SET is_active=0 WHERE id='gcu_report_filter'")
print("deactivated dead gcu_report_filter")
c.commit()
for r in cur.execute("SELECT id,name,type,is_active,is_global FROM function").fetchall(): print(r)
c.close()
