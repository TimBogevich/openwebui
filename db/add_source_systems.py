# -*- coding: utf-8 -*-
"""Append the official RZD SOURCE SYSTEM to each spravki/metrics table COMMENT,
so describe() surfaces it and the agent cites the real source (КАСАНТ, АРМ ОНД,
СИС Эффект, …) instead of the bare DB table name.

Source strings taken verbatim from the authoritative golden docx
(Образец экспертных вопросов.docx). Idempotent: skips if already present.

Run: python db/add_source_systems.py
"""
import subprocess

# table -> official source-system citation (as written in the golden report)
SOURCES = {
    'spravki_port_stations':
        "ИСТОЧНИК ДЛЯ ОТВЕТА: ЕМД ПП УР — Справки о работе припортовых станций.",
    'spravki_speed':
        "ИСТОЧНИК ДЛЯ ОТВЕТА: СИС Эффект — Справка о выполнении технической скорости / "
        "анализа участковой скорости по дорогам России.",
    'spravki_sort_stations':
        "ИСТОЧНИК ДЛЯ ОТВЕТА: ПК ИУС ЦУП НП — Справка анализа работы важнейших "
        "сортировочных станций сети ОАО РЖД.",
    'spravki_failures':
        "ИСТОЧНИК ДЛЯ ОТВЕТА: КАСАНТ — Суточная оперативная справка о случаях отказов "
        "в работе технических средств.",
    'spravki_speed_restrictions':
        "ИСТОЧНИК ДЛЯ ОТВЕТА: АСУ ВОП-2 — Справка об ограничениях скорости, не "
        "предусмотренных графиком движения поездов.",
    'spravki_delays':
        "ИСТОЧНИК ДЛЯ ОТВЕТА: ПК ИУС ЦУП НП — Справка о наличии задержанных поездов.",
    'spravki_locomotives':
        "ИСТОЧНИК ДЛЯ ОТВЕТА: АРМ ОНД — Справка Локомотивы.",
    'metrics':
        "ИСТОЧНИК ДЛЯ ОТВЕТА: Доклад СКИМ ОД (ежедневный доклад ЦГЦУ).",
}

MARK = "ИСТОЧНИК ДЛЯ ОТВЕТА:"

def psql(sql):
    return subprocess.run(
        ['docker','exec','gcu-postgres','psql','-U','postgres','-d','postgres','-tAc',sql],
        capture_output=True, text=True, encoding='utf-8').stdout.strip()

for tbl, src in SOURCES.items():
    cur = psql(f"SELECT obj_description('{tbl}'::regclass);")
    if not cur:
        print(f"skip (no comment / table): {tbl}"); continue
    if MARK in cur:
        print(f"skip (already has source): {tbl}"); continue
    new = (cur.rstrip() + " " + src).replace("'", "''")
    subprocess.run(['docker','exec','gcu-postgres','psql','-U','postgres','-d','postgres','-c',
                    f"COMMENT ON TABLE {tbl} IS '{new}';"], capture_output=True, text=True, encoding='utf-8')
    print(f"source added: {tbl} -> {src.split('—')[0].replace(MARK,'').strip()}")

print("done")
