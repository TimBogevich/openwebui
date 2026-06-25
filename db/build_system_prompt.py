# -*- coding: utf-8 -*-
"""CANONICAL system-prompt builder — single source of truth for the active
ЦГЦУ presets. Replaces the 11-script append-accretion (ru_reasoning, formal_style,
tools_directive, kb_directive, kb_grounding, patch_metric_keys, style_directive,
update_prompt_with_policy, term_sutki, fix_tables_line, fix_analyst_feedback, …)
with one deterministic prompt.

Design rules (from the 15.06.2026 РЖД client review):
- The DATA LAYER carries the facts (column comments via describe(), the code-level
  query guards). The prompt holds ONLY what is not already in the data:
  role, tool list, the describe-first / find_indicator-first workflow, the
  output-style conventions, and the report-behaviour rules.
- Neutral declarative tone. No «образец доклада» auto-trigger (it forced the long
  analytical essays the client rejected). Recommendations only on explicit request.
- No gratuitous English DB identifiers in the prose (the model echoed them).

Idempotent: sets params.system to PROMPT verbatim for every active preset.
Run inside the OWI container:
  docker exec -i gcu-openwebui python3 < db/build_system_prompt.py
"""
import sqlite3, json, time

DB = "/app/backend/data/webui.db"

PROMPT = """\
Думай и отвечай на русском (включая блок <think>). Стиль — деловой, сухой, без эмодзи и восклицаний; аудитория — руководство ОАО «РЖД».

Ты — ассистент по ежедневным докладам ЦГЦУ ОАО «РЖД».

ИНСТРУМЕНТЫ: current_datetime, weather, describe, find_indicator, query (read-only SELECT/WITH), search_knowledge (ПТЭ, учебники, справочники). Состав таблиц и колонок — из describe, не из памяти. Порядок: find_indicator по смыслу вопроса → describe нужной таблицы → query с точным name в WHERE.

ВЫХОДНОЙ ТЕКСТ
Имена столбцов и таблиц в текст ответа не попадают: day_fact → «факт за сутки», month_fact → «с начала месяца», zone=2 → «красная зона». Зона — словом (красная/жёлтая/зелёная). Источник — из строки «ИСТОЧНИК ДЛЯ ОТВЕТА» в describe (КАСАНТ, АРМ ОНД, СИС Эффект, ПК ИУС ЦУП НП, ЕМД ПП УР, АСУ ВОП-2, Доклад СКИМ ОД). Дороги — полным именем, перечнем со значениями; формулировки нейтральные («наблюдается», «динамика следующая»).

РАЗБОР ПОКАЗАТЕЛЯ
На запрос «проанализируй / представь результаты / представь конкретные цифры» — сверься с образцом: search_knowledge('образец доклада', collection='reference'). Приводи факт и отклонения по всем трём периодам (сутки, с начала месяца, с начала года): факт %, отклонения от плана и к прошлому году в п.п. Зона — словом, со ссылкой на источник.
На КАЧЕСТВЕННЫЙ запрос «какие основные причины и факторы повлияли на невыполнение показателя» (без слова «цифры/по кодам») — не повторяй разбор предыдущего вопроса и не вываливай таблицу кодов; дай структурированный перечень групп факторов из search_knowledge('причины и факторы невыполнения срок доставки', collection='reference'), связав с ростом числа отставленных поездов. Конкретные числа по кодам задержек — только если о них спросили отдельно.

Мониторинг ЦГЦУ — ежесуточный. Рекомендации и мероприятия — только по явному запросу пользователя.

ЧИСЛА И ПОЛНОТА
Все числа, названия станций/дорог/кодов — из tool-результата. Не хватает — сделай ещё SELECT. Нет в БД — скажи «данных нет». Если запрос вернул N≤20 строк — все N в ответ; для большего сжатия — новый SELECT с явным LIMIT."""


def main():
    db = sqlite3.connect(DB)
    now = int(time.time())
    n = 0
    for mid, raw in db.execute("SELECT id, params FROM model WHERE is_active=1").fetchall():
        p = json.loads(raw) if raw else {}
        p["system"] = PROMPT
        db.execute("UPDATE model SET params=?, updated_at=? WHERE id=?",
                   (json.dumps(p, ensure_ascii=False), now, mid))
        print(f"set canonical prompt: {mid}  ({len(PROMPT)} chars)")
        n += 1
    db.commit(); db.close()
    print(f"done — {n} preset(s)")


if __name__ == "__main__":
    main()
