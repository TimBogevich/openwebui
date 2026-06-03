# -*- coding: utf-8 -*-
"""Make the LOCAL LM Studio qwen3.5-9b use NATIVE MCP tool calling (the OWI
native loop is connection-agnostic — gated on function_calling=='native', not
on local-vs-remote). Bind the MCP tool, enable native FC, drop the filter."""
import sqlite3, json, time
c=sqlite3.connect('/app/backend/data/webui.db'); cur=c.cursor()
now=int(time.time())
mid="qwen/qwen3.5-9b"
r=cur.execute("SELECT params,meta FROM model WHERE id=?", (mid,)).fetchone()
params=json.loads(r[0]); meta=json.loads(r[1])
# enable native function calling; keep the russian system prompt
params["function_calling"]="native"
# bind MCP tool, drop filter
meta["toolIds"]=["server:mcp:gcu-postgres"]
meta["filterIds"]=[]
caps=meta.get("capabilities",{})
caps["tool_calling"]=True; caps["native_tool_calling"]=True
# drop the 25 builtin tools so the small ctx isn't bloated (keep only MCP)
caps["builtin_tools"]=False
meta["capabilities"]=caps
cur.execute("UPDATE model SET params=?, meta=?, updated_at=? WHERE id=?",
            (json.dumps(params,ensure_ascii=False), json.dumps(meta,ensure_ascii=False), now, mid))
c.commit()
print("local 9b updated:")
print("  function_calling:", params.get("function_calling"))
print("  toolIds:", meta["toolIds"], "filterIds:", meta["filterIds"])
print("  caps:", caps)
c.close()
