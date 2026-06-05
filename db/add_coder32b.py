# -*- coding: utf-8 -*-
"""Add qwen2.5-coder-32b-instruct (local, LM Studio) as an MCP-tool-calling
preset, cloning the working config from the existing local 27B."""
import sqlite3, json, time
DB="/app/backend/data/webui.db"
c=sqlite3.connect(DB); cur=c.cursor(); now=int(time.time())
uid=cur.execute("SELECT id FROM user WHERE role='admin' LIMIT 1").fetchone()[0]

# 1) whitelist the coder on the LM Studio connection [0] so it's exposed
cid,data=cur.execute("SELECT id,data FROM config ORDER BY id DESC LIMIT 1").fetchone()
d=json.loads(data)
cfg0=d["openai"]["api_configs"].setdefault("0",{})
mids=cfg0.get("model_ids",[])
if "qwen2.5-coder-32b-instruct" not in mids:
    mids.append("qwen2.5-coder-32b-instruct"); cfg0["model_ids"]=mids
cur.execute("UPDATE config SET data=?, updated_at=created_at WHERE id=?",(json.dumps(d,ensure_ascii=False),cid))
print("LM Studio whitelist now:", mids)

# 2) clone params/meta from the existing local 27B (it has the full ЦГЦУ prompt + S4)
base=cur.execute("SELECT params,meta FROM model WHERE id='qwen/qwen3.6-27b'").fetchone()
params=json.loads(base[0]); meta=json.loads(base[1])
params["function_calling"]="native"        # native MCP tool loop
meta["toolIds"]=["server:mcp:gcu-postgres"]
meta["filterIds"]=[]
meta.setdefault("capabilities",{})
meta["capabilities"].update({"tool_calling":True,"native_tool_calling":True,"builtin_tools":False})
meta["description"]=""
mid="qwen2.5-coder-32b-instruct"
cur.execute("DELETE FROM model WHERE id=?", (mid,))
cur.execute("INSERT INTO model (id,user_id,base_model_id,name,params,meta,updated_at,created_at,is_active) "
            "VALUES (?,?,?,?,?,?,?,?,1)",
            (mid, uid, None, "ЦГЦУ Кодер 32Б (локальный)",
             json.dumps(params,ensure_ascii=False), json.dumps(meta,ensure_ascii=False), now, now))
c.commit()
print("created preset: ЦГЦУ Кодер 32Б (локальный) ->", mid)
print("active models:", [r[0] for r in cur.execute("SELECT name FROM model WHERE is_active=1 ORDER BY name")])
c.close()
