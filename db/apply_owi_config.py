# -*- coding: utf-8 -*-
"""Apply GCU OWI config (models, filter, MCP tool server, openai connections)
directly into the container webui.db. Adapts URLs for Docker networking.
Reads /app/backend/data/_native_cfg.json (copied in)."""
import sqlite3, json, time, sys
DB="/app/backend/data/webui.db"
SRC="/app/backend/data/_native_cfg.json"
cfg=json.load(open(SRC,encoding="utf-8"))
now=int(time.time())
c=sqlite3.connect(DB); cur=c.cursor()
uid=cur.execute("SELECT id FROM user ORDER BY created_at LIMIT 1").fetchone()[0]
print("admin uid:", uid)

def dock(url):
    return (url.replace("http://localhost:1234","http://host.docker.internal:1234")
               .replace("http://127.0.0.1:1234","http://host.docker.internal:1234")
               .replace("http://localhost:8808","http://gcu-mcp:8808")
               .replace("http://127.0.0.1:8808","http://gcu-mcp:8808"))

# 1) wipe any existing models/functions (clean slate as requested)
cur.execute("DELETE FROM model"); cur.execute("DELETE FROM function")

# 2) models (3 qwen presets) — verbatim meta/params, owned by container admin
for m in cfg["models"]:
    cur.execute("INSERT INTO model (id,user_id,base_model_id,name,params,meta,updated_at,created_at,is_active) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (m["id"], uid, m["base_model_id"], m["name"],
                 json.dumps(m["params"],ensure_ascii=False), json.dumps(m["meta"],ensure_ascii=False),
                 now, now, m.get("is_active",1)))
print("models inserted:", cur.execute("SELECT count(*) FROM model").fetchone()[0])

# 3) filter function (verbatim content), global+active
f=cfg["filter"]
cur.execute("INSERT INTO function (id,user_id,name,type,content,meta,valves,is_active,is_global,updated_at,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f["id"], uid, f["name"], f["type"], f["content"],
             f["meta"], f["valves"], 1, 1, now, now))
print("filter inserted:", f["id"])

# 4) config table: merge openai (docker URLs) + tool_server (docker URL)
row=cur.execute("SELECT id,data FROM config ORDER BY id DESC LIMIT 1").fetchone()
data=json.loads(row[1])
oa=cfg["openai"]
oa["api_base_urls"]=[dock(u) for u in oa["api_base_urls"]]
data["openai"]=oa
ts=cfg["tool_server"]
for conn in ts["connections"]:
    conn["url"]=dock(conn["url"])
data["tool_server"]=ts
cur.execute("UPDATE config SET data=?, updated_at=? WHERE id=?", (json.dumps(data,ensure_ascii=False), now, row[0]))
print("openai urls:", oa["api_base_urls"])
print("tool_server url:", ts["connections"][0]["url"])

c.commit(); c.close()
print("DONE")
