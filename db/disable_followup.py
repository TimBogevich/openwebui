# -*- coding: utf-8 -*-
"""Disable Open WebUI's Follow-Up question generation (the auto-suggested
"Какие основные причины…" questions shown after each answer).

Sets task.follow_up.enable = false in the OWI config (webui.db `config` table).
Idempotent: re-running is a no-op if already disabled. Reversible: set REVERT=1.

Gotcha (per HANDOFF §10): config.updated_at is a DATETIME *string* — writing an
int epoch crash-loops OWI. We insert a fresh row with a proper timestamp string;
OWI reads the latest row by id.

Run inside the container:
    docker cp db/disable_followup.py gcu-openwebui:/tmp/
    docker exec gcu-openwebui python3 /tmp/disable_followup.py
"""
import sqlite3, json, os, datetime

DB = "/app/backend/data/webui.db"
REVERT = os.getenv("REVERT", "0") == "1"

conn = sqlite3.connect(DB)
cur = conn.cursor()
row = cur.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchone()
cfg_id, data = row
cfg = json.loads(data)

# ensure nested task.follow_up exists
task = cfg.setdefault("task", {})
follow = task.setdefault("follow_up", {})

target = True if REVERT else False
current = follow.get("enable", None)

if current == target:
    print(f"[no-op] task.follow_up.enable already = {target}")
    conn.close()
    raise SystemExit(0)

follow["enable"] = target
new_data = json.dumps(cfg, ensure_ascii=False)
# DATETIME string, NOT int epoch (crash-loop gotcha). No Date.now in scripts here,
# but this runs in the container's normal python — datetime is fine.
ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
cur.execute(
    "INSERT INTO config (data, version, created_at, updated_at) VALUES (?,?,?,?)",
    (new_data, cfg.get("version", 0), ts, ts),
)
conn.commit()
print(f"[ok] task.follow_up.enable: {current} -> {target} (new config row id {cur.lastrowid})")
conn.close()
