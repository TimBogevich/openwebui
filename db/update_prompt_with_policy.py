# -*- coding: utf-8 -*-
"""Add condensed query-policy hints to the MoE preset's system prompt.

These hints USED TO live in describe('metrics'). They are global behavior
(not schema description), so they belong in the system prompt — paid once
per chat, not on every describe() call.

Idempotent: re-running replaces the policy block, doesn't duplicate.
Run inside the gcu-openwebui container:
  docker exec -i gcu-openwebui python3 < db/update_prompt_with_policy.py
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
MODEL_ID = "qwen3.6-35b-a3b"
MARKER = "<!-- query-policy -->"

POLICY = (
    f"\n\n{MARKER}\n"
    "ПРАВИЛА ЗАПРОСОВ К БД:\n"
    "1. Перед SQL-запросом ВСЕГДА вызывай find_indicator('смысл вопроса') — "
    "получишь топ-5 реальных имён показателей с indicator_number, разделом и единицей. "
    "Затем используй name ДОСЛОВНО в WHERE m.name = '...' (НЕ ищи через ILIKE/% — это менее точно).\n"
    "2. Если SELECT вернул 0 строк или ошибку — НЕ повторяй похожий запрос. "
    "Перечитай ответ describe/find_indicator и измени подход или дай честный ответ «не найдено».\n"
    "3. indicator_number не уникален — фильтруй по name.\n"
    "4. Если данных за нужную дату нет (проверь min/max date в describe) — скажи прямо: "
    "«данные за эту дату отсутствуют», не зацикливайся."
)

c = sqlite3.connect(DB)
row = c.execute("SELECT params FROM model WHERE id=?", (MODEL_ID,)).fetchone()
if not row:
    raise SystemExit(f"preset {MODEL_ID} not found")
params = json.loads(row[0])
prompt = params.get("system", "")

# strip any existing policy block (idempotent)
if MARKER in prompt:
    prompt = prompt.split(MARKER)[0].rstrip()

new_prompt = prompt.rstrip() + POLICY
params["system"] = new_prompt
now = int(time.time())
c.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
          (json.dumps(params), now, MODEL_ID))
c.commit()
print(f"[OK] system prompt updated for {MODEL_ID}")
print(f"     new length: {len(new_prompt)} chars (was {len(prompt)})")
print(f"     policy block size: {len(POLICY)} chars")
c.close()
