# -*- coding: utf-8 -*-
"""Add a directive so models KNOW to call current_datetime / weather for
general questions (date, time, weather) instead of answering from memory.
Idempotent. Inserted before the role line."""
import sqlite3, json, time
DB="/app/backend/data/webui.db"
DIRECTIVE = (
 "ИНСТРУМЕНТЫ: у тебя есть инструменты помимо базы данных. Для вопросов о "
 "ТЕКУЩЕЙ дате/времени («какой сегодня день», «какое число», «сколько времени», "
 "«какой сейчас месяц/год») ВСЕГДА вызывай инструмент current_datetime — НЕ "
 "отвечай по памяти, твоя внутренняя дата устарела. Для вопросов о погоде вызывай "
 "weather. Для показателей докладов — describe и query. Не отказывайся от вызова "
 "инструмента, если он подходит к вопросу."
)
MARKER = "ИНСТРУМЕНТЫ:"
c=sqlite3.connect(DB); cur=c.cursor(); now=int(time.time())
for r in cur.execute("SELECT id,params FROM model WHERE is_active=1").fetchall():
    mid, params = r
    p=json.loads(params) if params else {}
    s=p.get("system","")
    if MARKER in s:
        print(f"  {mid}: already has tools directive"); continue
    # insert after the СТИЛЬ block (before the role «Ты —» line) if possible
    idx=s.find("\nТы —")
    if idx==-1: idx=s.find("\nТы —")
    if idx!=-1:
        s = s[:idx] + "\n\n" + DIRECTIVE + s[idx:]
    else:
        s = s + "\n\n" + DIRECTIVE
    p["system"]=s
    cur.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                (json.dumps(p,ensure_ascii=False), now, mid))
    print(f"  {mid}: tools directive added")
c.commit(); c.close(); print("done")
