# -*- coding: utf-8 -*-
"""Sharpen the anti-loop rule: hard-stop after 2-3 failed searches and report
what data IS available instead of spiraling. General behavior (any impossible/
ambiguous question), idempotent. Fixes the minutes-long «ILIKE '%код%'» loop on
questions whose data doesn't exist (e.g. «задержки по дорогам по коду 1»)."""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"
OLD = ("• Действуй, не зацикливайся: 1–3 запроса достаточно. Запрос вернул не то — "
       "меняй ФИЛЬТР или КЛЮЧ (зона / за_месяц), а не повторяй тот же запрос.")
NEW = ("• НЕ ЗАЦИКЛИВАЙСЯ (важно): максимум 3–4 запроса на поиск. Если после 2–3 попыток "
       "(с разными ФИЛЬТР/КЛЮЧ) данных НЕТ — ОСТАНОВИСЬ, не повторяй те же запросы и не рассуждай "
       "по кругу. Ответь коротко: (1) чего в данных НЕТ (напр. нет разбивки по дорогам, нет кодов "
       "причин задержек), (2) что ЕСТЬ рядом (напр. разрез по подразделениям ЦТ/ЦД/ЦДИ, "
       "отставленные поезда по погранпереходам), (3) предложи уточнить вопрос. Честный краткий "
       "ответ «такого разреза нет, есть вот это» ЛУЧШЕ бесконечного поиска. Один и тот же запрос "
       "не повторяй дважды.")

SENTINEL = "максимум 3–4 запроса на поиск"

c = sqlite3.connect(DB); cur = c.cursor(); now = int(time.time()); n = 0
for mid, raw in cur.execute("SELECT id, params FROM model WHERE is_active=1").fetchall():
    p = json.loads(raw) if raw else {}
    s = p.get("system", "")
    if not s or SENTINEL in s:
        print(f"skip (already sharpened): {mid}"); continue
    s = s.replace(OLD, NEW, 1) if OLD in s else (s + "\n" + NEW)
    p["system"] = s
    cur.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                (json.dumps(p, ensure_ascii=False), now, mid))
    print(f"sharpened: {mid}"); n += 1
c.commit(); c.close(); print(f"done — {n}")
