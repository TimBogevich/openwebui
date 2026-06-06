# -*- coding: utf-8 -*-
"""Add a GROUNDING rule to the KB directive. Problem observed: the model called
search_knowledge, received the real справочник data (e.g. Руководство ОАО РЖД with
exact codes Ц/ЦЗ-1/ЦЗ-ЦТ…), then ANSWERED FROM ITS OWN TRAINING MEMORY instead —
inventing generic department names with NO codes. Classic RAG grounding failure.

This forces: when search_knowledge returns data, answer STRICTLY from those
fragments — quote exact names/codes/wording, never fill from memory, and if the
fragments don't fully cover the question, say so rather than invent.

Idempotent (guarded by MARKER). Appends right after the БАЗА ЗНАНИЙ block.
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
MARKER = "ОПОРА НА ИСТОЧНИКИ:"
RULE = (
    " ОПОРА НА ИСТОЧНИКИ: когда ты получил фрагменты из search_knowledge — отвечай "
    "СТРОГО по ним. Бери названия, КОДЫ (Ц, ЦЗ-ЦТ, ЦФТО, ЦБС…), должности и формулировки "
    "ДОСЛОВНО из выданных фрагментов. НЕ добавляй пункты из собственной памяти и НЕ "
    "придумывай обобщённые названия — если их нет во фрагментах, их не существует в ответе. "
    "Для запросов «перечисли всё / полный список» используй k побольше (8–10) и перечисли "
    "ровно то, что вернул справочник, с кодами. Если фрагменты не покрывают вопрос "
    "полностью — прямо скажи, что в справочнике показана только эта часть, и предложи "
    "уточнить запрос. Лучше неполный, но ТОЧНЫЙ список из источника, чем полный по памяти."
)
# anchor: end of the existing KB directive
ANCHOR = "если есть профильная литература."

c = sqlite3.connect(DB); cur = c.cursor(); now = int(time.time())
for mid, params in cur.execute("SELECT id, params FROM model WHERE is_active=1").fetchall():
    p = json.loads(params) if params else {}
    s = p.get("system", "")
    if MARKER in s:
        print(f"  {mid}: already has grounding rule"); continue
    if ANCHOR in s:
        s = s.replace(ANCHOR, ANCHOR + RULE, 1)
    else:
        s = s + "\n\n" + RULE.strip()
    p["system"] = s
    cur.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                (json.dumps(p, ensure_ascii=False), now, mid))
    print(f"  {mid}: grounding rule added")
c.commit(); c.close(); print("done")
