# -*- coding: utf-8 -*-
"""Show ONLY «ЦГЦУ Ассистент 35Б MoE (локальный)» in the Open WebUI model dropdown.

Non-destructive — nothing is deleted, only hidden:
  1) deactivate every other model preset (is_active=0)
  2) trim the LM Studio connection whitelist to just qwen3.6-35b-a3b
     (so the raw 9b/27b/coder base models don't appear)
  3) disable the agentplatform (API) connection so no remote models show

Reversible: re-activate presets / restore whitelists / re-enable conn[1].
config.updated_at is a DATETIME string column — use CURRENT_TIMESTAMP, never int.
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
KEEP = "qwen3.6-35b-a3b"        # the only model id to remain visible

c = sqlite3.connect(DB); cur = c.cursor(); now = int(time.time())

# 1) deactivate all presets except the MoE
n = 0
for mid, name, act in cur.execute("SELECT id, name, is_active FROM model").fetchall():
    want = 1 if mid == KEEP else 0
    if act != want:
        cur.execute("UPDATE model SET is_active=?, updated_at=? WHERE id=?", (want, now, mid))
        print(f"  preset {'KEEP ' if want else 'hide '}: {name}")
        n += 1
print(f"  ({n} presets changed)")

# 2+3) trim connections in config
row = cur.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchone()
cfg_id, cfg = row[0], json.loads(row[1])
oai = cfg.get("openai", {})
cfgs = oai.get("api_configs", {})

# conn[0] = LM Studio: whitelist ONLY the MoE
if "0" in cfgs:
    cfgs["0"]["model_ids"] = [KEEP]
    cfgs["0"]["enable"] = True
    print(f"  conn0 (LM Studio) whitelist -> [{KEEP}]")
# conn[1] = agentplatform API: disable entirely
if "1" in cfgs:
    cfgs["1"]["enable"] = False
    print("  conn1 (agentplatform API) -> disabled")

cur.execute("UPDATE config SET data=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(cfg), cfg_id))

c.commit()
print("\nActive presets now:")
for mid, name in cur.execute("SELECT id, name FROM model WHERE is_active=1").fetchall():
    print(f"  {name}  [{mid}]")
c.close(); print("done")
