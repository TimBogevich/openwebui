# -*- coding: utf-8 -*-
"""
Self-contained creator for the ГЦУ (GCU) reporting database used by the AI
assistant. Builds the star schema + `gtsu_search` materialized view (the single
flat surface the LLM/MCP queries) and loads representative MOCK data so the
chat can answer real SQL questions offline — no dependency on the RZD cluster.

Run on the target machine's local PostgreSQL (e.g. the laptop's PostgreSQL 18):

    set PGHOST=127.0.0.1
    set PGPORT=5432
    set PGUSER=postgres
    set PGPASSWORD=<your local postgres password>
    set PGDATABASE=postgres
    python create_gtsu_db.py

Or pass a full URL:

    python create_gtsu_db.py "postgresql://postgres:pass@127.0.0.1:5432/postgres"

Idempotent: drops and recreates the gtsu_* objects each run. Works with either
psycopg (v3) or psycopg2 — whichever is installed.

After it runs, point the MCP postgres tool / Open WebUI at this database and the
model can query `gtsu_search`:

    SELECT indicator, unit, responsible,
           (metrics->>'сутки_к_плану')::float AS dev
    FROM gtsu_search
    WHERE report_date = '2022-03-31' AND color_marker = 2
    ORDER BY dev ASC LIMIT 10;
"""
import os
import sys
import json
import datetime as dt
import math

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# DB driver: prefer psycopg (v3), fall back to psycopg2.
# ---------------------------------------------------------------------------
def connect(dsn=None):
    params = dict(
        host=os.environ.get("PGHOST", "127.0.0.1"),
        port=int(os.environ.get("PGPORT", "5432")),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", "postgres"),
        dbname=os.environ.get("PGDATABASE", "postgres"),
    )
    try:
        import psycopg  # v3
        if dsn:
            return psycopg.connect(dsn, autocommit=False), "psycopg3"
        return psycopg.connect(**params, connect_timeout=8), "psycopg3"
    except ImportError:
        pass
    import psycopg2  # v2
    if dsn:
        return psycopg2.connect(dsn), "psycopg2"
    return psycopg2.connect(connect_timeout=8, **params), "psycopg2"


# ---------------------------------------------------------------------------
# Schema DDL — star schema + denormalized materialized view.
# ---------------------------------------------------------------------------
DDL = r"""
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

DROP MATERIALIZED VIEW IF EXISTS gtsu_search CASCADE;
DROP TABLE IF EXISTS fact_metric CASCADE;
DROP TABLE IF EXISTS fact_commentary CASCADE;
DROP TABLE IF EXISTS dim_indicator CASCADE;
DROP TABLE IF EXISTS dim_report CASCADE;

CREATE TABLE dim_report (
    id            SERIAL PRIMARY KEY,
    report_date   DATE NOT NULL UNIQUE,
    source_file   TEXT,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE dim_indicator (
    id              SERIAL PRIMARY KEY,
    section_code    TEXT NOT NULL,
    section_title   TEXT NOT NULL,
    item_number     TEXT,
    item_depth      INT,
    parent_path     TEXT,
    indicator       TEXT NOT NULL,
    full_indicator  TEXT,
    unit            TEXT,
    responsible     TEXT,
    sheet_name      TEXT,
    UNIQUE (section_code, item_number, indicator)
);
CREATE INDEX dim_indicator_resp_idx    ON dim_indicator (responsible);
CREATE INDEX dim_indicator_section_idx ON dim_indicator (section_code);
CREATE INDEX dim_indicator_item_idx    ON dim_indicator (item_number);

CREATE TABLE fact_metric (
    report_id     INT  NOT NULL REFERENCES dim_report(id)    ON DELETE CASCADE,
    indicator_id  INT  NOT NULL REFERENCES dim_indicator(id) ON DELETE CASCADE,
    metric_key    TEXT NOT NULL,
    metric_value  DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (report_id, indicator_id, metric_key)
);
CREATE INDEX fact_metric_indicator_idx ON fact_metric (indicator_id, metric_key);
CREATE INDEX fact_metric_key_idx       ON fact_metric (metric_key);

CREATE TABLE fact_commentary (
    report_id           INT NOT NULL REFERENCES dim_report(id)    ON DELETE CASCADE,
    indicator_id        INT NOT NULL REFERENCES dim_indicator(id) ON DELETE CASCADE,
    color_marker        INT,
    text_comment        TEXT,
    management_actions  TEXT,
    PRIMARY KEY (report_id, indicator_id)
);
"""

MV_DDL = r"""
CREATE MATERIALIZED VIEW gtsu_search AS
WITH m AS (
    SELECT report_id, indicator_id,
           jsonb_object_agg(metric_key, metric_value) AS metrics
    FROM fact_metric
    GROUP BY report_id, indicator_id
)
SELECT
    di.id            AS indicator_id,
    dr.id            AS report_id,
    dr.report_date,
    dr.source_file,
    di.sheet_name,
    di.section_code,
    di.section_title,
    di.item_number,
    di.item_depth,
    di.parent_path,
    di.indicator,
    di.full_indicator,
    di.unit,
    di.responsible,
    fc.color_marker,
    coalesce(m.metrics, '{}'::jsonb)  AS metrics,
    fc.text_comment,
    fc.management_actions,
    concat_ws(' ',
      'Доклад ГЦУ ОАО РЖД от ' || to_char(dr.report_date, 'DD.MM.YYYY') || '.',
      'Раздел ' || di.section_code || '. ' || di.section_title || '.',
      CASE WHEN di.item_number IS NOT NULL THEN 'Показатель № ' || di.item_number || '.' END,
      'Показатель: ' || di.indicator || '.',
      CASE WHEN di.unit        IS NOT NULL THEN 'Единица измерения: ' || di.unit || '.' END,
      CASE WHEN di.responsible IS NOT NULL THEN 'Ответственное подразделение: ' || di.responsible || '.' END,
      (SELECT string_agg(
          CASE WHEN abs(v::float) < 1 AND v::float <> 0
               THEN k || ' ' || to_char(v::float * 100, 'FM+0D00') || '%'
               ELSE k || ' ' || to_char(v::float, 'FM999G999G999D999') || coalesce(' '||di.unit,'')
          END, '; ')
       FROM jsonb_each_text(coalesce(m.metrics,'{}'::jsonb)) AS j(k, v)),
      CASE WHEN fc.text_comment       IS NOT NULL THEN 'Комментарий: ' || fc.text_comment END,
      CASE WHEN fc.management_actions IS NOT NULL THEN 'Управленческие решения: ' || fc.management_actions END
    ) AS narrative
FROM dim_indicator di
CROSS JOIN dim_report dr
LEFT JOIN m  ON m.indicator_id  = di.id AND m.report_id  = dr.id
LEFT JOIN fact_commentary fc ON fc.indicator_id = di.id AND fc.report_id = dr.id
WHERE m.metrics IS NOT NULL OR fc.report_id IS NOT NULL;

CREATE UNIQUE INDEX gtsu_search_pk     ON gtsu_search (report_id, indicator_id);
CREATE INDEX gtsu_search_date_idx      ON gtsu_search (report_date);
CREATE INDEX gtsu_search_section_idx   ON gtsu_search (section_code);
CREATE INDEX gtsu_search_item_idx      ON gtsu_search (item_number);
CREATE INDEX gtsu_search_resp_idx      ON gtsu_search (responsible);
CREATE INDEX gtsu_search_tsv_idx       ON gtsu_search USING GIN (to_tsvector('russian', coalesce(narrative,'')));
CREATE INDEX gtsu_search_trgm_idx      ON gtsu_search USING GIN (narrative gin_trgm_ops);
"""


# ---------------------------------------------------------------------------
# Mock indicators — representative ГЦУ daily-report rows.
# color_marker: 2 = red (worst), 1 = yellow, 0 = green/normal.
# Deviations are stored as fractions (e.g. -0.0979 = -9,79%).
# ---------------------------------------------------------------------------
INDICATORS = [
    # (section_code, section_title, item_number, indicator, unit, responsible, sheet,
    #  color, fact_sutki, sutki_k_planu, sutki_k_2021, comment, mgmt)
    ("I", "Грузовые перевозки", "1.1", "Погрузка, всего", "тыс. тонн", "ЦФТО", "Доклад Ц ЦЗ",
     1, 3412.5, -0.0215, 0.0182, "Снижение погрузки угля на Восточном полигоне", None),
    ("I", "Грузовые перевозки", "1.2", "Внутрироссийская погрузка", "тыс. тонн", "ЦФТО", "Доклад Ц ЦЗ",
     0, 2138.47, 0.0153, 0.021, None, None),
    ("I", "Грузовые перевозки", "1.3", "Экспортная погрузка", "тыс. тонн", "ЦФТО", "Доклад Ц ЦЗ",
     2, 1274.0, -0.0612, -0.031, "Отставание по экспорту в порты Дальнего Востока",
     "Целесообразно рассмотреть перераспределение порожняка"),
    ("II", "Перевозки", "2.1", "Приведённая работа", "млн. т-км", "ЦД", "Доклад Ц ЦЗ",
     0, 7891.2, 0.0045, 0.0321, None, None),
    ("II", "Перевозки", "2.2", "Грузооборот", "млн. т-км", "ЦД", "Доклад Ц ЦЗ",
     1, 6543.8, -0.018, 0.012, "Снижение к плану из-за ремонтных окон", None),
    ("II", "Перевозки", "2.3", "Коэффициент разрыва", "%", "ЦД", "Доклад Ц ЦЗ",
     1, 2.098, -0.019, -0.028, "Отклонение т.км эксплуатационных и тарифных", None),
    ("III", "Финансово-экономические показатели", "3.1", "Прибыль (EBITDA)", "млрд. руб.", "ЦФ", "Доклад Ц ЦЗ",
     0, 427.742, 0.0465, 0.0632, "EBITDA за 11 мес. составляет 444,5 млрд.руб. (109,7% к плану)", None),
    ("III", "Финансово-экономичес показатели", "3.2", "Рентабельность по EBITDA", "%", "ЦФ", "Доклад Ц ЦЗ",
     0, 21.805, 0.0625, -0.386, None, None),
    ("III", "Финансово-экономические показатели", "3.3", "Пассажирооборот", "млн. пасс-км", "ЦЛ", "Доклад Ц ЦЗ",
     0, 269.031, 0.0837, 0.1276, "С начала года 13 108 млн. пасс-км, 108,4% к плану", None),
    ("IV", "Оперативная информация", "4.1", "Электровозы", "ед.", "ЦТ", "Доклад Ц ЦЗ",
     2, 72.0, -0.0979, -0.0513, "Плановый вывод серии ВЛ80 на капремонт",
     "Рекомендуется ускорить выпуск из ремонта на Ростовском ЭРЗ"),
    ("IV", "Оперативная информация", "4.2", "Тепловозы", "ед.", "ЦТ", "Доклад Ц ЦЗ",
     2, 158.0, -0.0923, -0.0487, "Ремонтная кампания тепловозов", None),
    ("IV", "Оперативная информация", "4.3", "Приём поездов", "поезд.", "ЦД", "Доклад Ц ЦЗ",
     2, 1.0, -0.80, -0.55, "Принят 1 поезд, 20% от согласованного с КНР техплана",
     "Необходим контроль исполнения техплана с КНР"),
    ("V", "ИТ-инфраструктура", "5.1", "Доступность информационных систем", "%", "ЦИТ", "Доклад Ц ЦЗ",
     2, 90.32, -0.0968, -0.0321, "Плановые работы на ЦОД", None),
    ("VI", "Срок доставки", "6.1", "Срок доставки грузов", "сут.", "ЦД", "Срок доставки",
     1, 5.2, -0.04, -0.02, "Рост из-за инфраструктурных ограничений", None),
    ("VI", "Срок доставки", "6.2", "Маршрутная скорость", "км/сут", "ЦД", "Срок доставки",
     0, 412.0, 0.011, 0.03, None, None),
    ("VII", "Инвестиционная программа", "7.1", "Освоение инвестиций", "млрд. руб.", "ЦУКС", "Инвест",
     1, 88.4, -0.012, 0.05, "Отставание по графику строительно-монтажных работ", None),
]

# 15 daily reports (2022-03-17 … 2022-03-31). 03-31 is the "real" snapshot;
# earlier dates are a deterministic random-walk so trend queries work.
BASE_DATE = dt.date(2022, 3, 31)
N_DAYS = 15
METRIC_KEYS = ("факт_сутки", "сутки_к_плану", "сутки_к_2021")


def walk(base, i, amp):
    """Deterministic perturbation (no RNG import needed, reproducible)."""
    return base * (1 + math.sin(i * 0.7 + base) * amp)


def main():
    dsn = sys.argv[1] if len(sys.argv) > 1 else None
    conn, drv = connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()
    print(f"Connected via {drv}. Building schema...")
    cur.execute(DDL)

    # dim_report — 15 dates
    report_ids = {}
    for d in range(N_DAYS):
        rd = BASE_DATE - dt.timedelta(days=N_DAYS - 1 - d)
        cur.execute(
            "INSERT INTO dim_report (report_date, source_file) VALUES (%s, %s) RETURNING id",
            (rd, f"ГЦУ-{rd.strftime('%m-%d')}.xlsx"),
        )
        report_ids[rd] = cur.fetchone()[0]
    print(f"  dim_report: {len(report_ids)} dates")

    # dim_indicator
    ind_ids = []
    for row in INDICATORS:
        sc, st, num, ind, unit, resp, sheet = row[:7]
        cur.execute(
            """INSERT INTO dim_indicator
               (section_code, section_title, item_number, item_depth, parent_path,
                indicator, full_indicator, unit, responsible, sheet_name)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (sc, st, num, len(num.split(".")), st, ind, f"{st} > {ind}", unit, resp, sheet),
        )
        ind_ids.append(cur.fetchone()[0])
    print(f"  dim_indicator: {len(ind_ids)}")

    # fact_metric + fact_commentary across all dates
    n_metric = 0
    for idx, row in enumerate(INDICATORS):
        (sc, st, num, ind, unit, resp, sheet,
         color, fact, plan, year, comment, mgmt) = row
        iid = ind_ids[idx]
        for d in range(N_DAYS):
            rd = BASE_DATE - dt.timedelta(days=N_DAYS - 1 - d)
            rid = report_ids[rd]
            is_last = (d == N_DAYS - 1)
            vals = {
                "факт_сутки": fact if is_last else round(walk(fact, d, 0.02), 4),
                "сутки_к_плану": plan if is_last else round(plan + math.sin(d) * 0.005, 4),
                "сутки_к_2021": year if is_last else round(year + math.cos(d) * 0.005, 4),
            }
            for k in METRIC_KEYS:
                cur.execute(
                    "INSERT INTO fact_metric (report_id, indicator_id, metric_key, metric_value) VALUES (%s,%s,%s,%s)",
                    (rid, iid, k, vals[k]),
                )
                n_metric += 1
            # commentary only on the real date (and only where present)
            if is_last and (comment or mgmt or color is not None):
                cur.execute(
                    """INSERT INTO fact_commentary
                       (report_id, indicator_id, color_marker, text_comment, management_actions)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (rid, iid, color, comment, mgmt),
                )
            elif not is_last and color is not None:
                cur.execute(
                    "INSERT INTO fact_commentary (report_id, indicator_id, color_marker) VALUES (%s,%s,%s)",
                    (rid, iid, color),
                )
    print(f"  fact_metric: {n_metric} rows")

    print("Building gtsu_search materialized view + indexes...")
    cur.execute(MV_DDL)

    conn.commit()
    cur.execute("SELECT count(*) FROM gtsu_search")
    total = cur.fetchone()[0]
    cur.execute("SELECT count(DISTINCT report_date) FROM gtsu_search")
    dates = cur.fetchone()[0]
    print(f"\nDONE. gtsu_search: {total} rows across {dates} dates.")
    print("Sample query (red zone on the latest date):")
    cur.execute(
        """SELECT indicator, responsible,
                  round((metrics->>'сутки_к_плану')::numeric*100, 2) AS dev_pct
           FROM gtsu_search
           WHERE report_date = %s AND color_marker = 2
           ORDER BY dev_pct ASC""",
        (BASE_DATE,),
    )
    for r in cur.fetchall():
        print(f"   {r[0]} ({r[1]}): {r[2]}%")
    conn.close()


if __name__ == "__main__":
    main()
