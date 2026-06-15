# -*- coding: utf-8 -*-
"""Prepend a 'think in Russian' instruction to every active model's system
prompt so Qwen3's <think> reasoning is in Russian — works for both LM Studio
(local) and the agentplatform API (remote), since both run Qwen3."""
import sqlite3, json, time
DB="/app/backend/data/webui.db"
RU = ("Всегда рассуждай и думай ИСКЛЮЧИТЕЛЬНО на русском языке. "
      "Все размышления в блоке <think> веди по-русски. Отвечай по-русски.")
# A sensible default role for models whose system prompt is empty.
DEFAULT_ROLE = ("Ты — ассистент по ежедневным докладам ГЦУ "
                "(Главного центра управления) ОАО «РЖД». Отвечай кратко и по делу, "
                "опираясь на данные из базы; не выдумывай числа.")
c=sqlite3.connect(DB); cur=c.cursor(); now=int(time.time())
for r in cur.execute("SELECT id,name,params FROM model WHERE is_active=1").fetchall():
    p=json.loads(r[2]) if r[2] else {}
    sysp=(p.get("system") or "").strip()
    # strip any prior weaker variant so we don't stack duplicates
    for old in ["Рассуждай на русском языке. Думай по-русски.",
                "Думай по-русски.", "Рассуждай на русском языке."]:
        sysp=sysp.replace(old,"").strip()
    if not sysp:
        sysp=DEFAULT_ROLE
    if not sysp.startswith(RU):
        sysp=RU+"\n\n"+sysp
    p["system"]=sysp
    cur.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                (json.dumps(p,ensure_ascii=False), now, r[0]))
    print(f"  {r[1]:32} system now starts: {sysp[:70]!r}")
c.commit(); c.close()
print("done")
