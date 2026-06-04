# -*- coding: utf-8 -*-
"""Insert a formal-analytical / no-emoji style directive into every active
model's system prompt, right after the Russian-reasoning line. Idempotent."""
import sqlite3, json, time
DB="/app/backend/data/webui.db"
RU_LINE = ("Всегда рассуждай и думай ИСКЛЮЧИТЕЛЬНО на русском языке. "
           "Все размышления в блоке <think> веди по-русски. Отвечай по-русски.")
STYLE = ("СТИЛЬ ОБЩЕНИЯ: строгий деловой и аналитический. НЕ используй эмодзи, "
         "смайлы, восклицания и неформальные обороты. Пиши сухо, по существу, "
         "как в официальной аналитической записке для руководства ОАО «РЖД». "
         "Числа, проценты и факты — точно; без приукрашивания.")
c=sqlite3.connect(DB); cur=c.cursor(); now=int(time.time())
for r in cur.execute("SELECT id,name,params FROM model WHERE is_active=1").fetchall():
    p=json.loads(r[2]) if r[2] else {}
    sysp=(p.get("system") or "")
    if STYLE in sysp:
        print(f"  {r[1]:32} already has style directive"); continue
    # insert STYLE right after the RU reasoning line if present, else prepend
    if RU_LINE in sysp:
        sysp=sysp.replace(RU_LINE, RU_LINE+"\n\n"+STYLE, 1)
    else:
        sysp=STYLE+"\n\n"+sysp
    p["system"]=sysp
    cur.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                (json.dumps(p,ensure_ascii=False), now, r[0]))
    print(f"  {r[1]:32} style directive added")
c.commit(); c.close(); print("done")
