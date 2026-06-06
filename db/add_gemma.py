#!/usr/bin/env python3
"""Wire gemma-4-26b-a4b-qat into OWI as a selectable LOCAL model: whitelist it on
the LM Studio connection + create a ЦГЦУ preset cloned from the working 35Б MoE
preset (so it inherits the SAME system prompt — KB directive, grounding rule —
and the SAME tool bindings / native function-calling meta).

Idempotent: re-running updates the existing preset / leaves the whitelist clean.
NOTE: show_only_moe.py may have trimmed the LM Studio whitelist to just the MoE;
this re-adds gemma so it appears in the dropdown again.
Run inside the container:
  docker exec -i gcu-openwebui python3 < db/add_gemma.py
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
GEMMA_ID = "google/gemma-4-26b-a4b-qat"          # exact LM Studio model id
CLONE_FROM = "qwen3.6-35b-a3b"                   # working 35Б MoE preset (current prompt+tools)
NEW_NAME = "ЦГЦУ Ассистент Gemma 26Б (локальный)"

c = sqlite3.connect(DB)

# --- 1) whitelist gemma on LM Studio connection (api_configs['0']) ---
row = c.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchone()
cfg_id, cfg = row[0], json.loads(row[1])
ids = cfg["openai"]["api_configs"]["0"]["model_ids"]
if GEMMA_ID not in ids:
    ids.append(GEMMA_ID)
    # config.updated_at is a DATETIME STRING column — never write int epoch (crash-loop)
    c.execute("UPDATE config SET data=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
              (json.dumps(cfg), cfg_id))
    print(f"[whitelist] added {GEMMA_ID} to connection 0 -> {ids}")
else:
    print(f"[whitelist] {GEMMA_ID} already present -> {ids}")

# --- 2) clone the MoE preset into a new gemma preset ---
src = c.execute("SELECT user_id, params, meta FROM model WHERE id=?", (CLONE_FROM,)).fetchone()
if not src:
    raise SystemExit(f"clone source preset {CLONE_FROM} not found")
user_id, params, meta = src[0], src[1], src[2]   # reuse params (system prompt!) + meta (toolIds, native FC) verbatim
now = int(time.time())                            # model table uses INT epoch

existing = c.execute("SELECT id FROM model WHERE id=?", (GEMMA_ID,)).fetchone()
if existing:
    c.execute("UPDATE model SET name=?, params=?, meta=?, is_active=1, updated_at=? WHERE id=?",
              (NEW_NAME, params, meta, now, GEMMA_ID))
    print(f"[preset] updated existing '{NEW_NAME}'")
else:
    c.execute(
        "INSERT INTO model (id, user_id, base_model_id, name, params, meta, updated_at, created_at, is_active) "
        "VALUES (?,?,?,?,?,?,?,?,1)",
        (GEMMA_ID, user_id, None, NEW_NAME, params, meta, now, now))
    print(f"[preset] created '{NEW_NAME}' (base={GEMMA_ID})")

c.commit()
print("\n=== active presets now ===")
for mid, name in c.execute("SELECT id, name FROM model WHERE is_active=1 ORDER BY name"):
    print(f"  {name}  [{mid}]")
c.close()
