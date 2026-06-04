# -*- coding: utf-8 -*-
"""Replace the too-restrictive 'РАБОТА С ДАННЫМИ' block with an ANALYST-oriented
one: encourage aggregation/analysis (SUM/GROUP BY, доли, тренды, выводы) while
keeping the guardrails (доли != абсолюты, числа из результата, не выдумывать).
Idempotent: removes any prior data-block variant, then appends the new one."""
import sqlite3, json, time, re
DB="/app/backend/data/webui.db"

NEW = (
 "ТЫ — АНАЛИТИК, а не просто исполнитель SQL. Активно используй агрегирующие "
 "запросы (SUM, AVG, GROUP BY, оконные функции, доли от итога, динамику по датам), "
 "чтобы отвечать на аналитические вопросы — доли подразделений, рейтинги, тренды, "
 "сравнения. Делай выводы и интерпретируй цифры, как в аналитической записке для "
 "руководства, а не выдавай сырую таблицу. "
 "ТОЧНОСТЬ: числа бери из результата запроса, не выдумывай. Отклонения (к плану, "
 "к 2021) хранятся как доли — переводи в проценты и не складывай их с абсолютными "
 "величинами; для долей и процентов считай их корректно в самом SQL. Если данных "
 "для расчёта не хватает — скажи об этом прямо."
)

# patterns of prior blocks to strip before appending the new one
OLD_PREFIXES = ("РАБОТА С ДАННЫМИ:", "ТЫ — АНАЛИТИК")

c=sqlite3.connect(DB); cur=c.cursor(); now=int(time.time())
for mid, params in cur.execute("SELECT id,params FROM model WHERE is_active=1").fetchall():
    p=json.loads(params) if params else {}
    s=p.get("system","")
    # drop any existing data/analyst block (from the last paragraph break onward if it starts with a known prefix)
    for pref in OLD_PREFIXES:
        i=s.find(pref)
        if i!=-1:
            s=s[:i].rstrip()
    s=s.rstrip()+"\n\n"+NEW
    p["system"]=s
    cur.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                (json.dumps(p,ensure_ascii=False), now, mid))
    print(f"  {mid}: analyst block set")
c.commit(); c.close(); print("done")
