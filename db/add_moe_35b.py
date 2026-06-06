#!/usr/bin/env python3
"""Wire the MoE Qwen3.6-35B-A3B into OWI: whitelist it on the LM Studio
connection + create a ЦГЦУ preset cloned from the working 27Б-local one.

Idempotent: re-running updates the existing preset / leaves the whitelist clean.
Run inside the container:
  docker exec -i gcu-openwebui python3 < db/add_moe_35b.py
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
MOE_ID = "qwen3.6-35b-a3b"                       # exact LM Studio model id
CLONE_FROM = "qwen/qwen3.6-27b"                  # working 27Б local preset
NEW_NAME = "ЦГЦУ Ассистент 35Б MoE (локальный)"

c = sqlite3.connect(DB)

# --- 1) whitelist the MoE on LM Studio connection (api_configs['0']) ---
row = c.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchone()
cfg_id, cfg = row[0], json.loads(row[1])
ids = cfg["openai"]["api_configs"]["0"]["model_ids"]
if MOE_ID not in ids:
    ids.append(MOE_ID)
    # config.updated_at is a DATETIME STRING column — do NOT write int epoch (crash-loop)
    c.execute("UPDATE config SET data=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
              (json.dumps(cfg), cfg_id))
    print(f"[whitelist] added {MOE_ID} to connection 0 -> {ids}")
else:
    print(f"[whitelist] {MOE_ID} already present -> {ids}")

# --- 2) clone the 27Б-local preset into a new MoE preset ---
src = c.execute("SELECT user_id, params, meta FROM model WHERE id=?", (CLONE_FROM,)).fetchone()
user_id, params, meta = src[0], src[1], src[2]   # reuse params (system prompt!) + meta (toolIds, native FC) verbatim
now = int(time.time())                            # model table uses INT epoch

existing = c.execute("SELECT id FROM model WHERE id=?", (MOE_ID,)).fetchone()
if existing:
    c.execute("UPDATE model SET name=?, params=?, meta=?, is_active=1, updated_at=? WHERE id=?",
              (NEW_NAME, params, meta, now, MOE_ID))
    print(f"[preset] updated existing '{NEW_NAME}'")
else:
    c.execute(
        "INSERT INTO model (id, user_id, base_model_id, name, params, meta, updated_at, created_at, is_active) "
        "VALUES (?,?,?,?,?,?,?,?,1)",
        (MOE_ID, user_id, None, NEW_NAME, params, meta, now, now))
    print(f"[preset] created '{NEW_NAME}' (base={MOE_ID})")

c.commit()
print("\n=== active presets now ===")
for mid, name in c.execute("SELECT id, name FROM model WHERE is_active=1 ORDER BY name"):
    print(f"  {name}  [{mid}]")
c.close()
