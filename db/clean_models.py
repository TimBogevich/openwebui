# -*- coding: utf-8 -*-
"""Show ONLY 4 named GCU models, no descriptions, hide everything else
(embeddings, arena, raw base qwen entries)."""
import sqlite3, json, time
DB="/app/backend/data/webui.db"
c=sqlite3.connect(DB); cur=c.cursor()
now=int(time.time())

# --- 1. Rename the 4 presets + strip descriptions ---
# API models = no suffix; local models = "(локальный)"
RENAMES = {
    "qwen/qwen3.5-9b":         "ГЦУ Ассистент 9Б (локальный)",   # LM Studio local
    "qwen/qwen3.6-27b":        "ГЦУ Ассистент 27Б (локальный)",  # LM Studio local
    "remote-qwen/qwen3.5-9b":  "ГЦУ Ассистент 9Б",                # agentplatform API
    "remote-qwen/qwen3.6-27b": "ГЦУ Ассистент 27Б",               # agentplatform API
}
for mid, newname in RENAMES.items():
    row = cur.execute("SELECT meta FROM model WHERE id=?", (mid,)).fetchone()
    if not row:
        print("  (missing preset:", mid, ")"); continue
    meta = json.loads(row[0]) if row[0] else {}
    meta["description"] = ""                       # strip the comment line
    cur.execute("UPDATE model SET name=?, meta=?, is_active=1, updated_at=? WHERE id=?",
                (newname, json.dumps(meta, ensure_ascii=False), now, mid))
    print(f"  renamed {mid} -> {newname!r} (desc cleared)")

# --- 2. config: whitelist LM Studio to only the 2 qwen models + disable arena ---
cid, data = cur.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchone()
d = json.loads(data)
oa = d.setdefault("openai", {})
cfgs = oa.setdefault("api_configs", {})
# connection [0] = LM Studio (host.docker.internal:1234)
cfgs.setdefault("0", {})["model_ids"] = ["qwen/qwen3.5-9b", "qwen/qwen3.6-27b"]
# connection [1] = agentplatform — keep its whitelist (already the 2 qwen)
cfgs.setdefault("1", {}).setdefault("model_ids", ["qwen/qwen3.6-27b", "qwen/qwen3.5-9b"])
# disable arena models
d.setdefault("evaluation", {}).setdefault("arena", {})["enable"] = False
cur.execute("UPDATE config SET data=?, updated_at=created_at WHERE id=?",
            (json.dumps(d, ensure_ascii=False), cid))
print("  LM Studio whitelist:", cfgs["0"]["model_ids"])
print("  arena disabled")

c.commit()
print("\nFinal presets:")
for r in cur.execute("SELECT id,name,is_active FROM model ORDER BY name"):
    print(f"   {r[1]:32} (active={r[2]})")
c.close()
