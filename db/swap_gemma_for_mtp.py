#!/usr/bin/env python3
"""Replace Gemma preset with the new qwen3.6-35b-a3b-mtp preset in OWI.

- Adds qwen3.6-35b-a3b-mtp to LM Studio whitelist
- Creates «ЦГЦУ Ассистент 35Б MoE-MTP (локальный)» preset, cloned from current
  35Б MoE preset (same system prompt + same toolIds / native FC)
- Deactivates the Gemma preset and removes it from the whitelist

Idempotent. Reversible: re-run db/add_gemma.py to put Gemma back.
Run inside OWI container:
  docker exec -i gcu-openwebui python3 < db/swap_gemma_for_mtp.py
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
NEW_ID = "qwen3.6-35b-a3b-mtp"
NEW_NAME = "ЦГЦУ Ассистент 35Б MoE-MTP (локальный)"
CLONE_FROM = "qwen3.6-35b-a3b"
GEMMA_ID = "google/gemma-4-26b-a4b-qat"

c = sqlite3.connect(DB)

# --- 1) update LM Studio whitelist: add MTP, drop Gemma ---
row = c.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchone()
cfg_id, cfg = row[0], json.loads(row[1])
ids = cfg["openai"]["api_configs"]["0"]["model_ids"]
changed = False
if NEW_ID not in ids:
    ids.append(NEW_ID); changed = True
    print(f"[whitelist] added {NEW_ID}")
if GEMMA_ID in ids:
    ids.remove(GEMMA_ID); changed = True
    print(f"[whitelist] removed {GEMMA_ID}")
if changed:
    # config.updated_at is a DATETIME STRING column — never write int epoch
    c.execute("UPDATE config SET data=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
              (json.dumps(cfg), cfg_id))
print(f"[whitelist] now: {ids}")

# --- 2) create / update the MTP preset, cloned from the current MoE preset ---
src = c.execute("SELECT user_id, params, meta FROM model WHERE id=?", (CLONE_FROM,)).fetchone()
if not src:
    raise SystemExit(f"clone source preset {CLONE_FROM} not found")
user_id, params, meta = src[0], src[1], src[2]
now = int(time.time())

existing = c.execute("SELECT id FROM model WHERE id=?", (NEW_ID,)).fetchone()
if existing:
    c.execute("UPDATE model SET name=?, params=?, meta=?, is_active=1, updated_at=? WHERE id=?",
              (NEW_NAME, params, meta, now, NEW_ID))
    print(f"[preset] updated '{NEW_NAME}'")
else:
    c.execute(
        "INSERT INTO model (id, user_id, base_model_id, name, params, meta, updated_at, created_at, is_active) "
        "VALUES (?,?,?,?,?,?,?,?,1)",
        (NEW_ID, user_id, None, NEW_NAME, params, meta, now, now))
    print(f"[preset] created '{NEW_NAME}' (base={NEW_ID})")

# --- 3) deactivate Gemma preset ---
res = c.execute("UPDATE model SET is_active=0, updated_at=? WHERE id=? AND is_active=1",
                (now, GEMMA_ID))
if res.rowcount:
    print(f"[preset] deactivated Gemma ({GEMMA_ID})")
else:
    print(f"[preset] Gemma was not active — skip")

c.commit()
print("\n=== active presets now ===")
for mid, name in c.execute("SELECT id, name FROM model WHERE is_active=1 ORDER BY name"):
    print(f"  {name}  [{mid}]")
c.close()
