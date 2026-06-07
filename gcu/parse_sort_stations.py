# -*- coding: utf-8 -*-
"""Parser for «Справка Анализ работы важнейших сортировочных станций» xlsb.

Layout in source:
  Rows 1-5 = title + multi-row header
  From row 6: «Итого» (network total), then for each station 2 rows pair:
    - 'сут.' row: daily values
    - 'ср/сут' row: average daily values for the period
  Road code (ОКТ, МОСК, ГОРЬК, ...) appears in column A only on the
  first station row of each road; subsequent stations of same road have
  empty A. We carry the road forward until we see a new one.

Column positions (0-indexed) in the data rows:
  0 = road  (only on first station of each road)
  1 = station name
  2 = period ('сут.' | 'ср/сут')
  3 = working_park (rabochiy park)  [only on 'сут.' row]
  4 = rosp_total (k rospusku, всего)
  5 = arrived_trains (pribylo poezdov)  [only on 'сут.' row]
  6 = refused_trains (rasf. poezdov)
  7 = rosp_no_pere (k rospusku, with prevailing)
  8 = rosp_inner  (k rospusku, без pere)
  9 = formed_trains (sformirovano poezdov)
  10 = sent_trains (otpravleno poezdov)
  11 = avg_weight (sredniy ves)
  12 = avg_length (sredn usl. dlina)
  ... 13+ = additional metrics (stored as JSONB)
"""
import os, sys, json, argparse, datetime
import pyxlsb, psycopg

DB_URL = os.environ.get("GCU_DATABASE_URL",
                        "postgresql://postgres:Gcu2026!@gcu-postgres:5432/postgres")

VALID_ROADS = {
    "ОКТ", "КЛГ", "МОСК", "ГОРЬК", "СЕВ", "С-КАВ", "СКВ", "ЮВС", "Ю-ВОСТ",
    "ПРВ", "ПРИВ", "КБШ", "СВР", "СВЕРД", "ЮУР", "Ю-УР", "ЗСБ", "З-СИБ",
    "КРС", "КРАС", "ВСБ", "В-СИБ", "ЗАБ", "ДВС", "ДВОСТ",
}

def _num(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def parse(xlsb_path, report_date_str):
    report_date = datetime.date.fromisoformat(report_date_str)
    records = []

    with pyxlsb.open_workbook(xlsb_path) as wb:
        sheet_name = wb.sheets[0]
        with wb.get_sheet(sheet_name) as ws:
            rows = []
            for row in ws.rows():
                # Build dense list: cells include None for empty positions
                # but pyxlsb returns only non-empty cells. Use col index.
                d = {}
                for c in row:
                    d[c.c] = c.v
                rows.append(d)

    current_road = None

    for r_idx, row in enumerate(rows[5:], start=6):  # skip header rows 1-5
        col0 = row.get(0)
        col1 = row.get(1)
        col2 = row.get(2)

        # Detect new road code in column A
        if isinstance(col0, str):
            v = col0.strip()
            if v.upper() in VALID_ROADS or v in VALID_ROADS:
                current_road = v
                # data starts at col1 (station)
            elif v == "Итого":
                # network total row — emit with road='СЕТЬ', station='Итого'
                rec = {
                    "report_date": report_date,
                    "road": "СЕТЬ",
                    "station": "Итого",
                    "period": "сут.",
                }
                # Network row layout differs — first numeric is at col 6
                # Just dump available numeric data into raw_extra
                extra = {str(k): row[k] for k in row if k > 0 and isinstance(row[k], (int, float))}
                rec["raw_extra"] = json.dumps(extra, ensure_ascii=False) if extra else None
                # Try to grab working_park (col6 for total row)
                rec["working_park"] = _num(row.get(6))
                records.append(rec)
                continue
            else:
                # unknown text in col A — skip
                continue

        # Need a station name in col 1 and period in col 2
        if not isinstance(col1, str) or not isinstance(col2, str):
            continue
        station = col1.strip()
        period = col2.strip()
        if period not in ("сут.", "ср/сут"):
            continue
        if not station:
            continue

        rec = {
            "report_date":   report_date,
            "road":          current_road,
            "station":       station,
            "period":        period,
        }

        # Column mapping (positions verified against header rows 3-5):
        #   3 = working_park НОРМА  (target)
        #   4 = working_park на 18-00 (actual at 18:00)
        #   5 = working_park текущий (current snapshot)
        #   6 = К росп. на 18-00
        #   7 = Прибыло поездов всего
        #   8 = с пер (с переработкой)
        #   9 = без пер
        #  10 = Расф. поездов (расформировано)
        #  11 = Расф. вагонов
        #  15 = Сформ. поездов
        #  17 = Отпр. поездов
        #  19 = Средний вес
        #  21 = Ср. усл. длина
        # Both 'сут.' and 'ср/сут' use the same column positions for these values.
        # 'сут.' rows additionally hold the working_park НОРМА in col 3.
        if period == "сут.":
            rec["working_park"]   = _num(row.get(4))  # actual at 18:00 (more useful than норма)
        else:  # ср/сут
            rec["working_park"]   = _num(row.get(4))

        rec["rosp_total"]     = _num(row.get(6))
        rec["arrived_trains"] = _num(row.get(7))
        rec["refused_trains"] = _num(row.get(10))
        rec["rosp_no_pere"]   = _num(row.get(9))
        rec["formed_trains"]  = _num(row.get(15))
        rec["sent_trains"]    = _num(row.get(17))
        rec["avg_weight"]     = _num(row.get(19))
        rec["avg_length"]     = _num(row.get(21))

        # Store everything else as JSONB for forensic recovery
        extra_cols = {3,8,11,12,13,14,16,18,20,22,23,24,25,26,27,28}
        extra = {str(k): row[k] for k in row if k in extra_cols and isinstance(row[k], (int, float, str))}
        rec["raw_extra"] = json.dumps(extra, ensure_ascii=False) if extra else None

        records.append(rec)

    return records


def ingest(xlsb_path, report_date_str, force=False):
    recs = parse(xlsb_path, report_date_str)
    if not recs:
        print("[WARN] no records parsed")
        return 0
    conn = psycopg.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM spravki_sort_stations WHERE report_date=%s",
                        (datetime.date.fromisoformat(report_date_str),))
            for r in recs:
                cur.execute(
                    "INSERT INTO spravki_sort_stations "
                    "(report_date, road, station, period, working_park, rosp_total, "
                    " arrived_trains, refused_trains, rosp_no_pere, formed_trains, "
                    " sent_trains, avg_weight, avg_length, raw_extra) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                    (r["report_date"], r["road"], r["station"], r["period"],
                     r.get("working_park"), r.get("rosp_total"),
                     r.get("arrived_trains"), r.get("refused_trains"),
                     r.get("rosp_no_pere"), r.get("formed_trains"),
                     r.get("sent_trains"), r.get("avg_weight"),
                     r.get("avg_length"), r.get("raw_extra")))
        conn.commit()
        print(f"[OK] loaded {len(recs)} rows for {report_date_str}")
        return len(recs)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()
    ingest(args.file, args.date)
