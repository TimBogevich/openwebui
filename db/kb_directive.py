# -*- coding: utf-8 -*-
"""Add a routing directive so models KNOW to call search_knowledge for
NORMATIVE / THEORY / CONCEPTUAL questions (определения, причины, требования ПТЭ,
методики, классификации) — instead of only mining the ГЦУ report comments.

Problem this fixes: the model answered «какие причины отставания поездов» purely
from gtsu text_comment via SQL and never searched the literature, even saying
«в базе нет прямого перечня причин». It needs an explicit hint that a reference
library exists and WHEN to use it.

Idempotent (guarded by MARKER). Inserted right after the existing ИНСТРУМЕНТЫ block
if present, else appended.
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
MARKER = "БАЗА ЗНАНИЙ:"
DIRECTIVE = (
    "БАЗА ЗНАНИЙ: помимо оперативных докладов ГЦУ у тебя есть инструмент "
    "search_knowledge — поиск по СПРАВОЧНОЙ ЛИТЕРАТУРЕ РЖД (ПТЭ и приложения ИСИ/ИДП, "
    "учебники по эксплуатационной работе, плану формирования, графику движения, "
    "вагонопотокам). Вызывай search_knowledge для НОРМАТИВНЫХ, ТЕОРЕТИЧЕСКИХ и "
    "ПОНЯТИЙНЫХ вопросов: определения терминов, ПРИЧИНЫ и ФАКТОРЫ явлений, требования "
    "и правила (ПТЭ), методики и порядок расчёта, классификации. "
    "ПРАВИЛО ВЫБОРА: если вопрос про КОНКРЕТНЫЕ ЧИСЛА из ежедневного доклада (сколько, "
    "динамика, отклонение, зона за дату) — используй query. Если вопрос про то, ЧТО ЭТО "
    "ТАКОЕ, ПОЧЕМУ, КАКИЕ БЫВАЮТ, КАК ПОЛОЖЕНО по правилам — сначала вызови "
    "search_knowledge и обопрись на источники (для ПТЭ цитируй дословно, указывай пункт). "
    "Не ограничивайся текстовыми комментариями из gtsu, если есть профильная литература."
)
INSERT_AFTER = "Не отказывайся от вызова инструмента, если он подходит к вопросу."

c = sqlite3.connect(DB); cur = c.cursor(); now = int(time.time())
for mid, params in cur.execute("SELECT id, params FROM model WHERE is_active=1").fetchall():
    p = json.loads(params) if params else {}
    s = p.get("system", "")
    if MARKER in s:
        print(f"  {mid}: already has KB directive"); continue
    if INSERT_AFTER in s:
        s = s.replace(INSERT_AFTER, INSERT_AFTER + "\n\n" + DIRECTIVE, 1)
    else:
        s = s + "\n\n" + DIRECTIVE
    p["system"] = s
    cur.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                (json.dumps(p, ensure_ascii=False), now, mid))
    print(f"  {mid}: KB directive added")
c.commit(); c.close(); print("done")
