# -*- coding: utf-8 -*-
"""Add qwen/qwen3.5-9b as a REMOTE (agentplatform) MCP-capable model preset,
mirroring the working remote-qwen/qwen3.6-27b. Run inside gcu-openwebui."""
import sqlite3, json, time
DB="/app/backend/data/webui.db"
c=sqlite3.connect(DB); cur=c.cursor()
uid=cur.execute("SELECT id FROM user ORDER BY created_at LIMIT 1").fetchone()[0]
now=int(time.time())

# 1) whitelist qwen/qwen3.5-9b on the agentplatform connection ([1], prefix 'ap')
row=cur.execute("SELECT id,data,created_at FROM config ORDER BY id DESC LIMIT 1").fetchone()
d=json.loads(row[1])
cfg1=d["openai"]["api_configs"]["1"]
mids=cfg1.get("model_ids",[])
if "qwen/qwen3.5-9b" not in mids:
    mids.append("qwen/qwen3.5-9b"); cfg1["model_ids"]=mids
print("ap model_ids now:", mids)
# IMPORTANT: config table uses DATETIME strings, keep created_at, set updated_at to a string
cur.execute("UPDATE config SET data=?, updated_at=created_at WHERE id=?",
            (json.dumps(d,ensure_ascii=False), row[0]))

# 2) create remote 9B preset mirroring remote 27B (base_model_id = ap.<id>)
rid="remote-qwen/qwen3.5-9b"
meta={
  "profile_image_url":"/static/favicon.png",
  "description":"Удалённая Qwen 9B (api.agentplatform.ru) с tool calling (MCP) к БД ГЦУ",
  "capabilities":{"vision":False,"citations":True,"tool_calling":True,"native_tool_calling":True},
  "toolIds":["server:mcp:gcu-postgres"],
  "filterIds":[]
}
params={"max_tokens":8192,"temperature":0.2,"function_calling":"native"}
cur.execute("DELETE FROM model WHERE id=?", (rid,))
cur.execute("INSERT INTO model (id,user_id,base_model_id,name,params,meta,updated_at,created_at,is_active) "
            "VALUES (?,?,?,?,?,?,?,?,1)",
            (rid, uid, "ap.qwen/qwen3.5-9b", "GCU Remote (Qwen 9B API)",
             json.dumps(params,ensure_ascii=False), json.dumps(meta,ensure_ascii=False), now, now))
c.commit()
print("created preset:", rid, "-> base ap.qwen/qwen3.5-9b")
print("models now:", [r[0] for r in cur.execute("SELECT id FROM model")])
c.close()
