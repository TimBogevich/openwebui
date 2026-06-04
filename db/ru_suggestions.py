# -*- coding: utf-8 -*-
"""Set Russian ГЦУ-related prompt suggestions (the clickable starters under the
chat). Stored in config.ui.prompt_suggestions (PersistentConfig). Idempotent."""
import sqlite3, json
DB="/app/backend/data/webui.db"
SUGG = [
  {"title": ["Сводка по последнему докладу", "ключевые показатели и зоны"],
   "content": "Дай краткую сводку по последнему доступному докладу ЦГЦУ: общее число показателей, сколько в красной/жёлтой/зелёной зоне, и 3-5 самых проблемных позиций."},
  {"title": ["Красная зона", "что критично сегодня"],
   "content": "Покажи показатели в красной зоне за последнюю дату: наименование, ответственное подразделение и отклонение от плана в процентах. Сгруппируй по подразделениям."},
  {"title": ["Скорость доставки по дорогам", "лучшие и худшие"],
   "content": "Какие железные дороги показали самую высокую и самую низкую среднюю скорость доставки грузовых отправок за последнюю дату? Дай топ-5 и антитоп-5."},
  {"title": ["Динамика за месяц", "тренд по ключевому показателю"],
   "content": "Оцени динамику грузооборота в течение марта 2022: как менялся показатель к плану и к прошлому году от начала к концу месяца."},
  {"title": ["Сравнение подразделений", "выполнение плана"],
   "content": "Сравни подразделения (ЦД, ЦТ, ЦФТО и др.) по выполнению плана за последнюю дату: у кого больше всего отклонений в красную зону?"},
  {"title": ["Сводка по разделу", "финансы / перевозки / эксплуатация"],
   "content": "Сделай краткий аналитический обзор по разделу «Грузовые перевозки» за последнюю дату: основные показатели, отклонения и выводы."},
]
c=sqlite3.connect(DB); cur=c.cursor()
cid,data=cur.execute("SELECT id,data FROM config ORDER BY id DESC LIMIT 1").fetchone()
d=json.loads(data)
d.setdefault("ui",{})["prompt_suggestions"]=SUGG
cur.execute("UPDATE config SET data=?, updated_at=created_at WHERE id=?",(json.dumps(d,ensure_ascii=False),cid))
c.commit()
print("set", len(SUGG), "Russian suggestions")
for s in SUGG: print("  -", s["title"][0])
c.close()
