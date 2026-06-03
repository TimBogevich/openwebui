# -*- coding: utf-8 -*-
import sqlite3, json, sys
sys.stdout.reconfigure(encoding="utf-8")
c=sqlite3.connect(r"C:\llm\openwebui\data\webui.db"); cur=c.cursor()
out={}
out["models"]=[]
for r in cur.execute("SELECT id,user_id,base_model_id,name,params,meta,is_active FROM model"):
    out["models"].append(dict(id=r[0],user_id=r[1],base_model_id=r[2],name=r[3],
                              params=json.loads(r[4]) if r[4] else {}, meta=json.loads(r[5]) if r[5] else {}, is_active=r[6]))
fr=cur.execute("SELECT id,user_id,name,type,content,meta,valves,is_active,is_global FROM function WHERE id='gcu_report_filter'").fetchone()
out["filter"]=dict(id=fr[0],user_id=fr[1],name=fr[2],type=fr[3],content=fr[4],
                   meta=fr[5],valves=fr[6],is_active=fr[7],is_global=fr[8])
d=json.loads(cur.execute("SELECT data FROM config ORDER BY id DESC LIMIT 1").fetchone()[0])
out["openai"]=d.get("openai")
out["tool_server"]=d.get("tool_server")
json.dump(out, open(r"C:\llm\gcu-export\_native_cfg.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
# show the bits I will rewrite for docker
print("openai api_base_urls:", out["openai"]["api_base_urls"])
print("openai api_configs:", json.dumps(out["openai"]["api_configs"], ensure_ascii=False))
print("tool_server url:", out["tool_server"]["connections"][0]["url"])
for m in out["models"]:
    print("model", m["id"], "| meta.toolIds=", m["meta"].get("toolIds"), "| filterIds=", m["meta"].get("filterIds"),
          "| params.function_calling=", m["params"].get("function_calling"))
