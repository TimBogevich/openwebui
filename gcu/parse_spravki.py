# -*- coding: utf-8 -*-
"""
Parse all supplementary справки files for a given ГЦУ date and load into
the spravki_* tables.

Usage (inside gcu-watch or gcu-mcp):
    python parse_spravki.py --date 2026-03-12 --dir /data/spravki/2026-03-12/

Files expected in --dir:
    Справка о наличии задержанных поездов.xlsx
    Суточная оперативная справка о случаях отказов в работе технических средств.xlsx
    Справка Локомотивы.xlsx
    Справка о работе припортовых станций на ДВОСТ ж.д. *.xlsx
    Справка о работе припортовых станций на ОКТ ж.д. *.xlsx
    Справка о работе припортовых станций на СКАВ ж.д. *.xlsx
    Справка Анализ выполнения участковой скорости*.xlsb
    Справка о Выполнении технической скорости*.xlsb
"""
import os, re, sys, argparse, datetime
import openpyxl

try:
    import pyxlsb
    HAS_XLSB = True
except ImportError:
    HAS_XLSB = False

DB_URL = os.environ.get("GCU_DATABASE_URL",
                        "postgresql://postgres:Gcu2026!@gcu-postgres:5432/postgres")

ROADS_ROW = ["СЕТЬ","ОКТ","КЛГ","МСК","ГОР","СЕВ","СКВ","ЮВС","ПРВ","КБШ","СВР","ЮУР","ЗСБ","КРС","ВСБ","ЗАБ","ДВС"]


def _clean(v):
    if v is None: return None
    s = str(v).strip().replace('\xa0', ' ')
    return s if s else None


def _num(v):
    if v is None: return None
    try: return float(v)
    except: return None


# ---------------------------------------------------------------------------
# 1. Задержанные поезда
# ---------------------------------------------------------------------------
def parse_delays(path, report_date):
    """Parse 'Справка о наличии задержанных поездов.xlsx'.

    Layout: row5 = road headers, then pairs of rows (п-да / ваг) per code.
    Returns list of dicts for spravki_delays.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    # find road header row (contains 'Сеть' or 'СЕТЬ')
    header_idx = None
    for i, row in enumerate(rows):
        if any(str(v).strip().upper() in ('СЕТЬ', 'СЕТ') for v in row if v):
            header_idx = i
            break
    if header_idx is None:
        return []

    # road codes from header row — all non-empty cells after col0
    header_row = rows[header_idx]
    road_cols = {}  # col_index -> road_code
    for ci, v in enumerate(header_row):
        s = _clean(v)
        if s and ci > 0:
            road_cols[ci] = s.upper().strip()

    records = []
    code = None
    code_name = None
    train_row = None

    for row in rows[header_idx + 1:]:
        first = _clean(row[0]) if len(row) > 0 else None
        second = _clean(row[1]) if len(row) > 1 else None

        if not first and not second:
            continue

        # detect code row: starts with ˈˈXˈˈ or «XX» - Название
        m = re.match(r"[«\'\ˈ\"ˈ]+([\d]+)[»\'\ˈ\"ˈ]+\s*[-–—]\s*(.+)", first or "")
        if m:
            code = m.group(1).strip()
            code_name = m.group(2).strip()
            # check if п-да is on same row or next
            if second == 'п-да' or second == 'п-дa':
                train_row = row
            else:
                train_row = None
            continue

        if first == 'ВСЕГО':
            code = 'ВСЕГО'
            code_name = 'Итого все коды'
            if second == 'п-да' or second == 'п-дa':
                train_row = row
            continue

        # п-да row
        if second in ('п-да', 'п-дa') or (first is None and second and 'п' in str(second).lower()):
            train_row = row
            continue

        # ваг row — follows п-да
        if second == 'ваг' or (first is None and train_row is not None):
            wagon_row = row
            # emit records for each road
            for ci, road in road_cols.items():
                trains = None
                wagons = None
                if train_row is not None and ci < len(train_row):
                    trains = int(train_row[ci]) if isinstance(train_row[ci], (int, float)) else None
                if ci < len(wagon_row):
                    wagons = int(wagon_row[ci]) if isinstance(wagon_row[ci], (int, float)) else None
                if trains is not None or wagons is not None:
                    records.append(dict(
                        report_date=report_date, delay_code=code,
                        delay_name=code_name, road_code=road,
                        trains=trains, wagons=wagons
                    ))
            train_row = None
            continue

    return records


# ---------------------------------------------------------------------------
# 2. Отказы технических средств
# ---------------------------------------------------------------------------
def parse_failures(path, report_date):
    """Parse 'Суточная оперативная справка о случаях отказов.xlsx'.

    Layout: row8+ = dept, 2025, 2026, +/-%, resolved, registered, investigated
    Returns list of dicts for spravki_failures.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    # data starts after the row containing column numbers 1,2,3,4,5,6,7
    data_start = 0
    for i, row in enumerate(rows):
        nums = [v for v in row if isinstance(v, (int, float)) and 1 <= v <= 7]
        if len(nums) >= 4:
            data_start = i + 1
            break

    records = []
    for row in rows[data_start:]:
        # Label sits in col[0] for road rows, but col[1] for complex rows
        # (локомотивный/инфраструктурный комплекс) where col[0] is empty.
        dept = _clean(row[0]) if len(row) > 0 and row[0] else None
        if not dept and len(row) > 1 and row[1]:
            dept = _clean(row[1])
        if not dept or dept.startswith('Раздел') or (dept.startswith('ИТОГО') and len(dept) > 20):
            continue
        # skip section headers (all caps long strings)
        if dept.isupper() and len(dept) > 30:
            continue

        def gi(i):
            v = row[i] if i < len(row) else None
            if isinstance(v, (int, float)): return int(v) if v == int(v) else v
            return None

        def gf(i):
            v = row[i] if i < len(row) else None
            # Source mixes formats: text "38,46%" vs float fraction 0.322.
            # Excel stores %-formatted cells as fractions → scale to percent.
            if isinstance(v, float):
                return round(v * 100, 2)
            try: return float(str(v).replace('%','').replace(',','.').strip())
            except: return None

        # The dept name cell is merged across col[0:1], so the numeric block
        # always starts at index [2]: 2025, 2026, +/-%, resolved, registered, investigated.
        f25, f26 = gi(2), gi(3)
        pct = gf(4)
        resolved, registered, investigated = gi(5), gi(6), gi(7)

        if f25 is None and f26 is None:
            continue

        records.append(dict(
            report_date=report_date, dept=dept,
            failures_2025=f25, failures_2026=f26,
            change_pct=pct, resolved=resolved,
            registered=registered, investigated=investigated
        ))
    return records


# ---------------------------------------------------------------------------
# 3. Локомотивы
# ---------------------------------------------------------------------------
def parse_locomotives(path, report_date):
    """Parse 'Справка Локомотивы.xlsx'.

    Returns list of dicts for spravki_locomotives.
    Layout: section headers (переменный ток / постоянный ток / тепловозы),
    then rows: polygon/road, plan, '/', fact, '+/-'
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    records = []
    current_section = 'AC'  # переменный ток default
    current_polygon = None

    SECTION_KEYWORDS = {
        'переменный': 'AC',
        'постоянный': 'DC',
        'тепловоз': 'diesel',
        'хозяйственн': 'diesel_hoz',
    }
    POLYGON_KEYWORDS = ['юго-зап', 'северо-зап', 'восточн', 'западн']

    for row in rows:
        vals = [v for v in row if v is not None]
        if not vals:
            continue

        first = _clean(row[0]) if len(row) > 0 else None
        if not first:
            continue

        # section header
        fl = first.lower()
        for kw, sec in SECTION_KEYWORDS.items():
            if kw in fl:
                current_section = sec
                break

        # polygon header
        for kw in POLYGON_KEYWORDS:
            if kw in fl:
                current_polygon = first.strip()
                break

        # data row: road/polygon name + numbers
        nums = [v for v in row if isinstance(v, (int, float)) and v != 0 or isinstance(v, str) and v.strip() in ('+/-', '/')]
        numeric = [v for v in row if isinstance(v, (int, float))]

        if len(numeric) >= 2 and first and not any(kw in fl for kw in ['содержание','анализ','таблиц','страниц','справк','резерв','общий','эс5','вл1']):
            # try to extract plan/fact/delta triplets separated by '/'
            # row structure: road, plan, '/', fact, '+/-' OR plan, '/', fact repeating
            road_name = first.strip()
            # collect numeric positions
            num_vals = [(i, v) for i, v in enumerate(row) if isinstance(v, (int, float))]
            # first two non-slash numbers are plan, fact
            if len(num_vals) >= 2:
                plan = num_vals[0][1] if num_vals else None
                fact = num_vals[1][1] if len(num_vals) > 1 else None
                delta = num_vals[2][1] if len(num_vals) > 2 else None
                records.append(dict(
                    report_date=report_date,
                    section=current_section,
                    polygon=current_polygon,
                    road=road_name,
                    plan=int(plan) if plan is not None else None,
                    fact=int(fact) if fact is not None else None,
                    delta=int(delta) if delta is not None else None,
                ))
    return records


# ---------------------------------------------------------------------------
# 4. Припортовые станции
# ---------------------------------------------------------------------------
def parse_port_stations(path, report_date, road_code):
    """Parse 'Справка о работе припортовых станций на X ж.д..xlsx'."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    # FIXED column layout (0-based tuple indices), header occupies rows 0-3:
    #   [0] station            [1] погрузка всего   [2] погрузка ср/сут
    #   [3] вагоны норма        [4] вагоны факт      [5] отставл. поездов
    #   [6] на дороге норма     [7] на дороге факт   [8] на дороге отставл.
    #   [9] налич. на станции   [10] перераб. спос.  [11] ВЫГРУЗКА на 18:00
    #   [12] выгрузка ср/сут    [13] налич. 06:00    [14] ...
    records = []
    for row in rows[4:]:
        station = _clean(row[0]) if len(row) > 0 and row[0] else None
        if not station or len(station) < 3:
            continue
        # skip leftover header/label rows
        if any(w in station.lower() for w in ['справ', 'погруз', 'налич', 'норма', 'перер']):
            continue

        def g(i):
            return _num(row[i]) if i < len(row) and isinstance(row[i], (int, float)) else None

        load_plan    = g(1)    # погрузка всего
        load_fact    = g(11)   # ВЫГРУЗКА факт на 18:00
        capacity     = g(10)   # перерабатывающая способность
        wagons_total = g(4)    # наличие вагонов факт
        wagons_road  = g(7)    # на дороге факт
        detained     = g(5)    # отставленных поездов

        if load_fact is None and capacity is None and wagons_total is None:
            continue

        records.append(dict(
            report_date=report_date, road=road_code, station=station,
            load_plan=load_plan, load_fact=load_fact, capacity=capacity,
            wagons_total=int(wagons_total) if wagons_total else None,
            wagons_road=int(wagons_road) if wagons_road else None,
            detained_trains=int(detained) if detained else None,
        ))
    return records


# ---------------------------------------------------------------------------
# 5. Скорость (участковая + техническая)
# ---------------------------------------------------------------------------
def parse_speed_xlsb(path, report_date, speed_type):
    """Parse xlsb speed справки. Returns list of dicts for spravki_speed."""
    if not HAS_XLSB:
        print("  pyxlsb not available — skipping", path)
        return []

    records = []
    with pyxlsb.open_workbook(path) as wb:
        for sh in wb.sheets:
            with wb.get_sheet(sh) as ws:
                all_rows = list(ws.rows())
                # find data rows: first cell is a road name (string, not header)
                for row in all_rows:
                    vals = [c.v for c in row]
                    first = _clean(vals[0]) if vals else None
                    if not first or len(first) < 3:
                        continue
                    # skip title/header rows
                    if any(kw in first.lower() for kw in ['анализ','выполнен','справ','дорога','таблиц','страниц','гвц','за от']):
                        continue
                    numerics = [_num(c.v) for c in row[1:] if isinstance(c.v, (int, float))]
                    if len(numerics) < 3:
                        continue

                    road = first.strip()
                    # columns: prev_year, norm, day_fact, day_delta, month_fact, month_delta, year_delta
                    records.append(dict(
                        report_date=report_date, speed_type=speed_type, road=road,
                        prev_year=numerics[0] if len(numerics) > 0 else None,
                        norm=numerics[1] if len(numerics) > 1 else None,
                        day_fact=numerics[2] if len(numerics) > 2 else None,
                        day_delta=numerics[3] if len(numerics) > 3 else None,
                        month_fact=numerics[4] if len(numerics) > 4 else None,
                        month_delta=numerics[5] if len(numerics) > 5 else None,
                        year_delta=numerics[6] if len(numerics) > 6 else None,
                    ))
    return records


# ---------------------------------------------------------------------------
# DB write helpers
# ---------------------------------------------------------------------------
def _delete_date(conn, table, report_date):
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table} WHERE report_date = %s", (report_date,))


def write_delays(conn, records):
    sql = """INSERT INTO spravki_delays
             (report_date,delay_code,delay_name,road_code,trains,wagons)
             VALUES (%s,%s,%s,%s,%s,%s)"""
    with conn.cursor() as cur:
        for r in records:
            cur.execute(sql, (r['report_date'],r['delay_code'],r['delay_name'],
                              r['road_code'],r['trains'],r['wagons']))


def write_failures(conn, records):
    sql = """INSERT INTO spravki_failures
             (report_date,dept,failures_2025,failures_2026,change_pct,resolved,registered,investigated)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"""
    with conn.cursor() as cur:
        for r in records:
            cur.execute(sql, (r['report_date'],r['dept'],r['failures_2025'],r['failures_2026'],
                              r['change_pct'],r['resolved'],r['registered'],r['investigated']))


def write_locomotives(conn, records):
    sql = """INSERT INTO spravki_locomotives
             (report_date,section,polygon,road,plan,fact,delta)
             VALUES (%s,%s,%s,%s,%s,%s,%s)"""
    with conn.cursor() as cur:
        for r in records:
            cur.execute(sql, (r['report_date'],r['section'],r['polygon'],r['road'],
                              r['plan'],r['fact'],r['delta']))


def write_port_stations(conn, records):
    sql = """INSERT INTO spravki_port_stations
             (report_date,road,station,load_plan,load_fact,capacity,wagons_total,wagons_road,detained_trains)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    with conn.cursor() as cur:
        for r in records:
            cur.execute(sql, (r['report_date'],r['road'],r['station'],
                              r['load_plan'],r['load_fact'],r['capacity'],r['wagons_total'],
                              r['wagons_road'],r['detained_trains']))


def write_speed(conn, records):
    sql = """INSERT INTO spravki_speed
             (report_date,speed_type,road,prev_year,norm,day_fact,day_delta,month_fact,month_delta,year_delta)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    with conn.cursor() as cur:
        for r in records:
            cur.execute(sql, (r['report_date'],r['speed_type'],r['road'],
                              r['prev_year'],r['norm'],r['day_fact'],r['day_delta'],
                              r['month_fact'],r['month_delta'],r['year_delta']))


# ---------------------------------------------------------------------------
# Main ingest
# ---------------------------------------------------------------------------
def ingest_dir(dirpath, report_date_str, force=False):
    import psycopg
    report_date = datetime.date.fromisoformat(report_date_str)
    conn = psycopg.connect(DB_URL)

    try:
        # ── задержанные ──
        f = _find(dirpath, 'задержанных поездов')
        if f:
            print(f"  [delays] {os.path.basename(f)}")
            _delete_date(conn, 'spravki_delays', report_date)
            recs = parse_delays(f, report_date)
            write_delays(conn, recs)
            print(f"    → {len(recs)} rows")
        else:
            print("  [delays] not found — skip")

        # ── отказы ──
        f = _find(dirpath, 'отказов в работе')
        if f:
            print(f"  [failures] {os.path.basename(f)}")
            _delete_date(conn, 'spravki_failures', report_date)
            recs = parse_failures(f, report_date)
            write_failures(conn, recs)
            print(f"    → {len(recs)} rows")
        else:
            print("  [failures] not found — skip")

        # ── локомотивы ──
        f = _find(dirpath, 'локомотив', ci=True)
        if f:
            print(f"  [locomotives] {os.path.basename(f)}")
            _delete_date(conn, 'spravki_locomotives', report_date)
            recs = parse_locomotives(f, report_date)
            write_locomotives(conn, recs)
            print(f"    → {len(recs)} rows")
        else:
            print("  [locomotives] not found — skip")

        # ── припортовые ──
        _delete_date(conn, 'spravki_port_stations', report_date)
        for road_kw, road_code in [('двост', 'ДВОСТ'), ('окт', 'ОКТ'), ('скав', 'СКАВ')]:
            f = _find(dirpath, f'припортовых.*{road_kw}')
            if f:
                print(f"  [ports:{road_code}] {os.path.basename(f)}")
                recs = parse_port_stations(f, report_date, road_code)
                write_port_stations(conn, recs)
                print(f"    → {len(recs)} rows")

        # ── скорость xlsb ──
        _delete_date(conn, 'spravki_speed', report_date)
        for kw, stype in [('участков', 'section'), ('технической скорости', 'technical')]:
            f = _find(dirpath, kw, exts=['.xlsb'])
            if f:
                print(f"  [speed:{stype}] {os.path.basename(f)}")
                recs = parse_speed_xlsb(f, report_date, stype)
                write_speed(conn, recs)
                print(f"    → {len(recs)} rows")
            else:
                print(f"  [speed:{stype}] not found — skip")

        conn.commit()
        print(f"\n  [OK] ingest complete for {report_date_str}")
    except Exception as e:
        conn.rollback()
        import traceback; traceback.print_exc()
        raise
    finally:
        conn.close()


def _find(dirpath, pattern, ci=False, exts=None):
    """Find file matching regex pattern in dirpath."""
    flags = re.IGNORECASE if ci else 0
    pat = re.compile(pattern, re.IGNORECASE)
    for fname in os.listdir(dirpath):
        if exts and not any(fname.lower().endswith(e) for e in exts):
            continue
        if pat.search(fname):
            return os.path.join(dirpath, fname)
    return None


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True, help='YYYY-MM-DD')
    ap.add_argument('--dir', required=True, help='directory with справки files')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    print(f"Ingesting справки for {args.date} from {args.dir}")
    ingest_dir(args.dir, args.date, args.force)
