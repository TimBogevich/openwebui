# -*- coding: utf-8 -*-
"""Load db/spravki_speed_restrictions_data.json into spravki_speed_restrictions.

The source xlsx stored data as a PNG image inside the file, so values were
extracted manually from the picture into the JSON. This loader reads that JSON
and writes one row per (road, date) pair. Idempotent: deletes existing rows
for the covered dates before inserting.
"""
import os, json, datetime, psycopg

DB_URL = os.environ.get("GCU_DATABASE_URL",
                        "postgresql://postgres:Gcu2026!@gcu-postgres:5432/postgres")

def load(json_path):
    data = json.load(open(json_path, encoding="utf-8"))
    plan_date = datetime.date.fromisoformat(data["plan_date"])
    fact_dates = [datetime.date.fromisoformat(d) for d in data["fact_dates"]]
    all_dates = [plan_date] + fact_dates

    conn = psycopg.connect(DB_URL)
    n_plan = n_fact = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM spravki_speed_restrictions WHERE report_date = ANY(%s)",
                (all_dates,))

            for road_entry in data["roads"]:
                road = road_entry["name"]
                # plan row
                plan = road_entry["plan"]
                cur.execute(
                    "INSERT INTO spravki_speed_restrictions "
                    "(report_date, road, row_type, restrictions, restrictions_km, "
                    " ratio_pct, delta_km) VALUES (%s,%s,'plan',%s,%s,%s,%s)",
                    (plan_date, road, int(plan[0]), float(plan[1]),
                     road_entry.get("ratio_pct"), road_entry.get("delta_km")))
                n_plan += 1

                # fact rows — skip _extra (not a real date)
                for d in fact_dates:
                    key = d.isoformat()
                    fact = road_entry["facts"].get(key)
                    if not fact:
                        continue
                    cur.execute(
                        "INSERT INTO spravki_speed_restrictions "
                        "(report_date, road, row_type, restrictions, restrictions_km) "
                        "VALUES (%s,%s,'fact',%s,%s)",
                        (d, road, int(fact[0]), float(fact[1])))
                    n_fact += 1

        conn.commit()
        print(f"[OK] loaded {n_plan} plan rows + {n_fact} fact rows")
        print(f"     date range: {plan_date} .. {fact_dates[-1]}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "/tmp/spravki_speed_restrictions_data.json"
    load(p)
