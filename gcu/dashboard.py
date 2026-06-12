# -*- coding: utf-8 -*-
"""
Dashboard generator for ЦГЦУ reports — April 2026.
Produces a self-contained static HTML file with embedded data and Chart.js charts.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal

import psycopg


def _json_default(o):
    """Make psycopg Decimal values (from SQL trunc/numeric) JSON-serializable."""
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

DB_URL = os.environ.get(
    "GCU_DATABASE_URL",
    "postgresql://postgres:Gcu2026!@127.0.0.1:5432/postgres",
)

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop", "ЦГЦУ отчеты")
INDEX_HTML = os.path.join(DESKTOP, "index.html")


# ---------------------------------------------------------------------------
# Data queries
# ---------------------------------------------------------------------------

def _fetch_dashboard_data():
    """Query all dashboard data for April 2026."""
    data = {}

    with psycopg.connect(DB_URL, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            # --- April date range ---
            cur.execute(
                "SELECT min(r.report_date), max(r.report_date), count(DISTINCT r.report_date) "
                "FROM metrics m JOIN reports r ON m.report_id = r.id "
                "WHERE r.report_date BETWEEN '2026-04-01' AND '2026-04-30'"
            )
            dmin, dmax, ndays = cur.fetchone()
            data["date_min"] = str(dmin) if dmin else "2026-04-01"
            data["date_max"] = str(dmax) if dmax else "2026-04-30"
            data["n_days"] = ndays or 0

            # --- Summary cards (last April date from reports) ---
            cur.execute(
                "SELECT red_count, yellow_count, green_count, metrics_count "
                "FROM reports WHERE report_date BETWEEN '2026-04-01' AND '2026-04-30' "
                "ORDER BY report_date DESC LIMIT 1"
            )
            r = cur.fetchone()
            if r:
                data["red_count"], data["yellow_count"], data["green_count"], data["total_metrics"] = r
            else:
                data["red_count"] = data["yellow_count"] = data["green_count"] = data["total_metrics"] = 0

            # --- Daily trends for key indicators ---
            key_indicators = [
                ("Погрузка общая", "погрузка общая", "млн т"),
                ("Доля отправок в срок", "доля груз. отправок в груж. вагонах с собл. установл. срока доставки", "%"),
                ("Участковая скорость", "участковая скорость", "км/ч"),
                ("Средний вес поезда", "средний вес грузового поезда", "т"),
            ]
            trends = {}
            for label, _, unit in key_indicators:
                try:
                    cur.execute(
                        "SELECT r.report_date, m.day_fact FROM metrics m "
                        "JOIN reports r ON m.report_id = r.id "
                        "WHERE r.report_date BETWEEN '2026-04-01' AND '2026-04-30' "
                        "AND lower(m.name) = %s AND m.road IS NULL "
                        "ORDER BY r.report_date", (label.lower(),)
                    )
                    rows = cur.fetchall()
                    if rows:
                        trends[label] = {"unit": unit, "data": [[str(r[0]), r[1]] for r in rows]}
                except Exception:
                    conn.rollback()
            data["trends"] = trends

            # --- Zone distribution per department (last April date) ---
            cur.execute(
                "SELECT m.responsible, coalesce(d.name, m.responsible) as dept_name, "
                "m.zone, count(*) as cnt "
                "FROM metrics m "
                "JOIN reports r ON m.report_id = r.id "
                "LEFT JOIN dept_codes d ON d.code = m.responsible "
                "WHERE r.report_date = (SELECT max(report_date) FROM reports "
                "  WHERE report_date BETWEEN '2026-04-01' AND '2026-04-30') "
                "AND m.zone IN (0,1,2) "
                "GROUP BY m.responsible, d.name, m.zone "
                "ORDER BY dept_name, m.zone"
            )
            data["dept_zones"] = [[d[1], d[2], d[3]] for d in cur.fetchall()]

            # --- Top red-zone indicators ---
            cur.execute(
                "SELECT m.name, m.responsible, m.unit, trunc(m.day_to_plan::numeric * 100, 2) as plan_dev_pct, "
                "trunc(m.day_fact::numeric, 2) as fact "
                "FROM metrics m "
                "JOIN reports r ON m.report_id = r.id "
                "WHERE r.report_date = (SELECT max(report_date) FROM reports "
                "  WHERE report_date BETWEEN '2026-04-01' AND '2026-04-30') "
                "AND m.zone = 2 AND m.road IS NULL "
                "ORDER BY m.day_to_plan ASC LIMIT 15"
            )
            data["red_indicators"] = [
                [r[0], r[1], r[2], r[3], r[4]] for r in cur.fetchall()
            ]

            # --- Personnel: key dates ---
            cur.execute(
                "SELECT r.report_date, m.day_fact FROM metrics m "
                "JOIN reports r ON m.report_id = r.id "
                "WHERE r.report_date IN ('2026-04-01','2026-04-17') "
                "AND lower(m.name) = lower('численность персонала на рабочих местах') "
                "AND m.road IS NULL ORDER BY r.report_date"
            )
            personnel = {}
            for dt, val in cur.fetchall():
                personnel[str(dt)] = val
            data["personnel"] = personnel

            # --- Delivery trend ---
            cur.execute(
                "SELECT r.report_date, trunc(m.day_fact::numeric, 2), "
                "trunc(m.day_to_plan::numeric * 100, 2) "
                "FROM metrics m "
                "JOIN reports r ON m.report_id = r.id "
                "WHERE r.report_date BETWEEN '2026-04-01' AND '2026-04-30' "
                "AND lower(m.name) = lower('доля груз. отправок в груж. вагонах с собл. установл. срока доставки') "
                "AND m.road IS NULL ORDER BY r.report_date"
            )
            data["delivery_daily"] = [[str(r[0]), r[1], r[2]] for r in cur.fetchall()]

            # --- Speed trend ---
            cur.execute(
                "SELECT r.report_date, trunc(m.day_fact::numeric, 1) "
                "FROM metrics m "
                "JOIN reports r ON m.report_id = r.id "
                "WHERE r.report_date BETWEEN '2026-04-01' AND '2026-04-30' "
                "AND lower(m.name) = lower('участковая скорость') "
                "AND m.road IS NULL ORDER BY r.report_date"
            )
            data["speed_daily"] = [[str(r[0]), r[1]] for r in cur.fetchall()]

            # --- Investment summary ---
            try:
                cur.execute(
                    "SELECT trunc(sum(exp_fact_or_forecast) / 1e9, 1) as exp_bln, "
                    "trunc(avg(exp_pct_to_period), 1) as exp_pct "
                    "FROM investment_metrics "
                    "WHERE EXISTS (SELECT 1 FROM report_sheets s JOIN reports r ON s.report_id = r.id "
                    "  WHERE s.id = investment_metrics.sheet_id "
                    "  AND r.report_date BETWEEN '2026-04-01' AND '2026-04-30')"
                )
                inv_row = cur.fetchone()
                if inv_row and inv_row[0] is not None:
                    data["investment"] = {"expenses_bln": inv_row[0], "expenses_pct": inv_row[1]}
                else:
                    data["investment"] = {"expenses_bln": 0, "expenses_pct": 0}
            except Exception:
                conn.rollback()
                data["investment"] = {"expenses_bln": 0, "expenses_pct": 0}

            # --- Delay summary ---
            try:
                cur.execute(
                    "SELECT count(*) FROM spravki_delays "
                    "WHERE report_date BETWEEN '2026-04-01' AND '2026-04-30'"
                )
                dr = cur.fetchone()
                data["delays"] = {"total_delayed_trains": dr[0] if dr else 0}
            except Exception:
                conn.rollback()
                data["delays"] = {"total_delayed_trains": 0}

    return data


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def _generate_html(data: dict) -> str:
    """Produce a self-contained dashboard HTML with embedded data."""

    ndays = data.get("n_days", 0)
    dmin = data.get("date_min", "2026-04-01")
    dmax = data.get("date_max", "2026-04-30")

    red = data.get("red_count", 0)
    yellow = data.get("yellow_count", 0)
    green = data.get("green_count", 0)
    total = data.get("total_metrics", 0) or (red + yellow + green) or 1

    trends_json = json.dumps(data.get("trends", {}), ensure_ascii=False, default=_json_default)
    dept_zones_json = json.dumps(data.get("dept_zones", []), ensure_ascii=False, default=_json_default)
    red_indicators_json = json.dumps(data.get("red_indicators", []), ensure_ascii=False, default=_json_default)
    personnel_json = json.dumps(data.get("personnel", {}), ensure_ascii=False, default=_json_default)
    delivery_json = json.dumps(data.get("delivery_daily", []), ensure_ascii=False, default=_json_default)
    speed_json = json.dumps(data.get("speed_daily", []), ensure_ascii=False, default=_json_default)
    inv_json = json.dumps(data.get("investment", {}), ensure_ascii=False, default=_json_default)
    delays_json = json.dumps(data.get("delays", {}), ensure_ascii=False, default=_json_default)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ЦГЦУ — Оперативный дашборд, апрель 2026</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.8/dist/chart.umd.min.js"></script>
<style>
:root {{
  --bg: #1e1e24;
  --card: #2a2a32;
  --text: #e0e0e4;
  --muted: #8e8e96;
  --red: #d32f2f;
  --yellow: #f9a825;
  --green: #2bb24c;
  --accent: #c62828;
  --border: #3a3a42;
  --rzd-red: #d50000;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}}
.header {{
  background: linear-gradient(135deg, #1a1a20 0%, #252530 100%);
  border-bottom: 3px solid var(--rzd-red);
  padding: 16px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}}
.header-left {{ display:flex; align-items:center; gap:16px; }}
.header-logo {{
  width: 42px; height: 42px;
  background: var(--rzd-red);
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 900; font-size: 18px; color: #fff;
}}
.header-title h1 {{ font-size:20px; font-weight:600; letter-spacing:0.5px; }}
.header-title span {{ font-size:12px; color:var(--muted); }}
.header-date {{
  background: var(--card);
  padding: 8px 20px;
  border-radius: 8px;
  font-size: 14px;
  color: var(--muted);
}}
.container {{ max-width:1400px; margin:0 auto; padding:24px 32px; }}

.cards {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:16px; margin-bottom:28px; }}
.card {{
  background: var(--card);
  border-radius: 10px;
  padding: 20px 24px;
  border-left: 4px solid var(--border);
}}
.card.red {{ border-left-color: var(--red); }}
.card.yellow {{ border-left-color: var(--yellow); }}
.card.green {{ border-left-color: var(--green); }}
.card.neutral {{ border-left-color: #607d8b; }}
.card-label {{ font-size:11px; text-transform:uppercase; letter-spacing:1px; color:var(--muted); margin-bottom:6px; }}
.card-value {{ font-size:32px; font-weight:700; }}
.card-sub {{ font-size:12px; color:var(--muted); margin-top:4px; }}
.card.red .card-value {{ color: var(--red); }}
.card.yellow .card-value {{ color: var(--yellow); }}
.card.green .card-value {{ color: var(--green); }}

.section {{ margin-bottom:32px; }}
.section-title {{
  font-size:14px; font-weight:600; text-transform:uppercase; letter-spacing:1px;
  color:var(--muted); margin-bottom:16px; padding-bottom:8px;
  border-bottom:1px solid var(--border);
}}
.chart-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(460px, 1fr)); gap:20px; }}
.chart-box {{
  background: var(--card);
  border-radius: 10px;
  padding: 20px;
}}
.chart-box h3 {{ font-size:13px; font-weight:500; color:var(--muted); margin-bottom:12px; }}
.chart-wrap {{ position:relative; height:280px; }}
.chart-wrap canvas {{ width:100% !important; }}

.table-box {{
  background: var(--card);
  border-radius: 10px;
  padding: 20px;
  margin-bottom:20px;
}}
.table-box h3 {{ font-size:13px; font-weight:500; color:var(--muted); margin-bottom:12px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ text-align:left; padding:8px 12px; border-bottom:1px solid var(--border); font-weight:500; color:var(--muted); font-size:11px; text-transform:uppercase; }}
td {{ padding:8px 12px; border-bottom:1px solid rgba(255,255,255,.04); }}
tr:hover td {{ background:rgba(255,255,255,.02); }}
.zone-dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; }}
.zone-dot.red {{ background:var(--red); }}
.zone-dot.yellow {{ background:var(--yellow); }}
.zone-dot.green {{ background:var(--green); }}
.badge {{
  display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600;
}}
.badge.red {{ background:rgba(211,47,47,.15); color:var(--red); }}
.badge.yellow {{ background:rgba(249,168,37,.15); color:var(--yellow); }}
.badge.green {{ background:rgba(43,178,76,.15); color:var(--green); }}

.personnel-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:16px; }}
.pers-card {{
  background: var(--card);
  border-radius: 10px;
  padding: 16px 20px;
  text-align: center;
}}
.pers-card .pers-date {{ font-size:11px; color:var(--muted); text-transform:uppercase; }}
.pers-card .pers-value {{ font-size:28px; font-weight:700; margin-top:4px; }}
.pers-card .pers-delta {{ font-size:12px; margin-top:4px; }}

.footer {{
  text-align: center;
  padding: 24px;
  color: var(--muted);
  font-size: 11px;
  border-top: 1px solid var(--border);
  margin-top: 40px;
}}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="header-logo">РЖД</div>
    <div class="header-title">
      <h1>ЦГЦУ — Оперативный дашборд</h1>
      <span>Главный центр управления ОАО «РЖД»</span>
    </div>
  </div>
  <div class="header-date">Апрель 2026 · {ndays} дат · {dmin} – {dmax}</div>
</div>

<div class="container">

<div class="cards">
  <div class="card neutral">
    <div class="card-label">Всего показателей</div>
    <div class="card-value">{total}</div>
    <div class="card-sub">на последнюю дату</div>
  </div>
  <div class="card red">
    <div class="card-label">Красная зона</div>
    <div class="card-value">{red}</div>
    <div class="card-sub">{round(red/total*100, 1) if total else 0}% показателей</div>
  </div>
  <div class="card yellow">
    <div class="card-label">Жёлтая зона</div>
    <div class="card-value">{yellow}</div>
    <div class="card-sub">{round(yellow/total*100, 1) if total else 0}% показателей</div>
  </div>
  <div class="card green">
    <div class="card-label">Зелёная зона</div>
    <div class="card-value">{green}</div>
    <div class="card-sub">{round(green/total*100, 1) if total else 0}% показателей</div>
  </div>
</div>

<div class="section" id="trends-section"></div>
<div class="section" id="red-section"></div>
<div class="section" id="personnel-section"></div>
<div class="chart-grid" id="extra-charts"></div>

</div>

<div class="footer">
  ОАО «Российские железные дороги» · ЦГЦУ · Данные на {dmax} · Автоматическая генерация
</div>

<script>
var DASHBOARD_DATA = {{
  trends: {trends_json},
  deptZones: {dept_zones_json},
  redIndicators: {red_indicators_json},
  personnel: {personnel_json},
  delivery: {delivery_json},
  speed: {speed_json},
  investment: {inv_json},
  delays: {delays_json},
  nDays: {ndays},
  redCount: {red},
  yellowCount: {yellow},
  greenCount: {green},
  totalMetrics: {total},
}};

var COLORS = {{ red: '#d32f2f', yellow: '#f9a825', green: '#2bb24c', neutral: '#607d8b' }};

(function() {{
  var section = document.getElementById('trends-section');
  var trends = DASHBOARD_DATA.trends;
  var keys = Object.keys(trends);
  if (!keys.length) return;

  var title = document.createElement('div');
  title.className = 'section-title';
  title.textContent = 'Динамика ключевых показателей';
  section.appendChild(title);

  var grid = document.createElement('div');
  grid.className = 'chart-grid';

  keys.forEach(function(key) {{
    var t = trends[key];
    var labels = t.data.map(function(d) {{ return d[0]; }});
    var values = t.data.map(function(d) {{ return d[1]; }});
    var box = document.createElement('div');
    box.className = 'chart-box';
    box.innerHTML = '<h3>' + key + ' (' + t.unit + ')</h3><div class="chart-wrap"><canvas></canvas></div>';
    grid.appendChild(box);

    new Chart(box.querySelector('canvas'), {{
      type: 'line',
      data: {{
        labels: labels,
        datasets: [{{
          label: key,
          data: values,
          borderColor: COLORS.red,
          backgroundColor: 'rgba(211,47,47,0.05)',
          fill: true,
          tension: 0.2,
          pointRadius: 2,
          borderWidth: 2,
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          x: {{ ticks: {{ color: '#8e8e96', maxRotation: 45, font: {{ size: 10 }} }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
          y: {{ ticks: {{ color: '#8e8e96' }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }}
        }}
      }}
    }});
  }});
  section.appendChild(grid);
}})();

(function() {{
  var section = document.getElementById('red-section');
  var items = DASHBOARD_DATA.redIndicators;
  if (!items.length) return;

  var title = document.createElement('div');
  title.className = 'section-title';
  title.textContent = 'Показатели в красной зоне (на последнюю дату)';
  section.appendChild(title);

  var box = document.createElement('div');
  box.className = 'table-box';
  var html = '<table><thead><tr><th>Показатель</th><th>Подразделение</th><th>Ед.</th><th>Факт</th><th>Откл. от плана, %</th><th>Зона</th></tr></thead><tbody>';
  items.forEach(function(r) {{
    html += '<tr>';
    html += '<td>' + r[0] + '</td>';
    html += '<td>' + (r[1] || '—') + '</td>';
    html += '<td>' + (r[2] || '—') + '</td>';
    html += '<td>' + (r[4] != null ? r[4] : '—') + '</td>';
    html += '<td>' + (r[3] != null ? r[3] : '—') + '</td>';
    html += '<td><span class="badge red">красная</span></td>';
    html += '</tr>';
  }});
  html += '</tbody></table>';
  box.innerHTML = '<h3>Топ-' + items.length + ' критичных показателей</h3>' + html;
  section.appendChild(box);

  var deptZones = DASHBOARD_DATA.deptZones;
  if (deptZones.length) {{
    var deptBox = document.createElement('div');
    deptBox.className = 'table-box';
    var deptHtml = '<table><thead><tr><th>Подразделение</th><th>Зелёная</th><th>Жёлтая</th><th>Красная</th></tr></thead><tbody>';

    var deptMap = {{}};
    deptZones.forEach(function(d) {{
      var name = d[0], zone = d[1], cnt = d[2];
      if (!deptMap[name]) deptMap[name] = {{0:0,1:0,2:0}};
      deptMap[name][zone] = (deptMap[name][zone] || 0) + cnt;
    }});

    var deptKeys = Object.keys(deptMap).sort();
    deptKeys.forEach(function(dk) {{
      var z = deptMap[dk];
      deptHtml += '<tr>';
      deptHtml += '<td>' + dk + '</td>';
      deptHtml += '<td><span class="zone-dot green"></span>' + (z[0] || 0) + '</td>';
      deptHtml += '<td><span class="zone-dot yellow"></span>' + (z[1] || 0) + '</td>';
      deptHtml += '<td><span class="zone-dot red"></span>' + (z[2] || 0) + '</td>';
      deptHtml += '</tr>';
    }});
    deptHtml += '</tbody></table>';
    deptBox.innerHTML = '<h3>Распределение зон по подразделениям</h3>' + deptHtml;
    section.appendChild(deptBox);
  }}
}})();

(function() {{
  var section = document.getElementById('personnel-section');
  var pers = DASHBOARD_DATA.personnel;
  var keys = Object.keys(pers).sort();
  if (!keys.length) return;

  var title = document.createElement('div');
  title.className = 'section-title';
  title.textContent = 'Численность персонала';
  section.appendChild(title);

  var grid = document.createElement('div');
  grid.className = 'personnel-grid';

  keys.forEach(function(dt, i) {{
    var val = pers[dt];
    var card = document.createElement('div');
    card.className = 'pers-card';
    card.innerHTML = '<div class="pers-date">' + dt + '</div><div class="pers-value">' + (val != null ? (val >= 1000 ? (val/1000).toFixed(1) + ' тыс.' : val) : '—') + '</div>';
    if (i > 0 && keys[i-1] in pers && val != null && pers[keys[i-1]] != null) {{
      var delta = val - pers[keys[i-1]];
      var sign = delta >= 0 ? '+' : '';
      var cl = delta >= 0 ? 'green' : 'red';
      card.innerHTML += '<div class="pers-delta" style="color:' + COLORS[cl] + '">' + sign + (Math.abs(delta) >= 1000 ? (Math.abs(delta)/1000).toFixed(1) + ' тыс.' : Math.abs(delta)) + '</div>';
    }}
    grid.appendChild(card);
  }});
  section.appendChild(grid);
}})();

(function() {{
  var container = document.getElementById('extra-charts');
  var delivery = DASHBOARD_DATA.delivery;
  if (!delivery.length) return;

  var box = document.createElement('div');
  box.className = 'chart-box';
  box.innerHTML = '<h3>Доля отправок в срок (%) — дневной факт и отклонение от плана</h3><div class="chart-wrap"><canvas></canvas></div>';
  container.appendChild(box);

  new Chart(box.querySelector('canvas'), {{
    type: 'line',
    data: {{
      labels: delivery.map(function(d) {{ return d[0]; }}),
      datasets: [
        {{
          label: 'Факт, %',
          data: delivery.map(function(d) {{ return d[1]; }}),
          borderColor: COLORS.neutral,
          backgroundColor: 'rgba(96,125,139,0.05)',
          fill: true,
          tension: 0.2,
          pointRadius: 2,
          borderWidth: 2,
          yAxisID: 'y',
        }},
        {{
          label: 'Откл. от плана, п.п.',
          data: delivery.map(function(d) {{ return d[2]; }}),
          borderColor: COLORS.red,
          borderDash: [4,4],
          tension: 0.2,
          pointRadius: 2,
          borderWidth: 1.5,
          yAxisID: 'y1',
        }}
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#8e8e96', font: {{ size: 10 }} }} }} }},
      scales: {{
        x: {{ ticks: {{ color: '#8e8e96', maxRotation: 45, font: {{ size: 10 }} }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
        y:  {{ type: 'linear', position: 'left', ticks: {{ color: '#8e8e96' }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
        y1: {{ type: 'linear', position: 'right', ticks: {{ color: '#d32f2f' }}, grid: {{ display: false }} }},
      }}
    }}
  }});

  var speed = DASHBOARD_DATA.speed;
  if (speed.length) {{
    var speedBox = document.createElement('div');
    speedBox.className = 'chart-box';
    speedBox.innerHTML = '<h3>Участковая скорость (км/ч)</h3><div class="chart-wrap"><canvas></canvas></div>';
    container.appendChild(speedBox);

    new Chart(speedBox.querySelector('canvas'), {{
      type: 'line',
      data: {{
        labels: speed.map(function(d) {{ return d[0]; }}),
        datasets: [{{
          label: 'Участковая скорость',
          data: speed.map(function(d) {{ return d[1]; }}),
          borderColor: '#ff9800',
          backgroundColor: 'rgba(255,152,0,0.05)',
          fill: true,
          tension: 0.2,
          pointRadius: 2,
          borderWidth: 2,
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          x: {{ ticks: {{ color: '#8e8e96', maxRotation: 45, font: {{ size: 10 }} }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
          y: {{ ticks: {{ color: '#8e8e96' }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }}
        }}
      }}
    }});
  }}

  var inv = DASHBOARD_DATA.investment;
  if (inv && inv.expenses_bln) {{
    var invBox = document.createElement('div');
    invBox.className = 'table-box';
    invBox.innerHTML = '<h3>Инвестиционная программа</h3>' +
      '<table><tr><td>Освоение за период</td><td><b>' + inv.expenses_bln + ' млрд руб.</b></td></tr>' +
      '<tr><td>% к плану периода</td><td><b>' + (inv.expenses_pct || '—') + '%</b></td></tr></table>';
    container.appendChild(invBox);
  }}

  var delays = DASHBOARD_DATA.delays;
  if (delays && delays.total_delayed_trains) {{
    var delBox = document.createElement('div');
    delBox.className = 'table-box';
    delBox.innerHTML = '<h3>Задержанные поезда</h3>' +
      '<table><tr><td>Всего фактов за апрель</td><td><b>' + delays.total_delayed_trains + '</b></td></tr></table>';
    container.appendChild(delBox);
  }}
}})();
</script>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build() -> str:
    """Generate the dashboard HTML file and return its filesystem path.
    The file can be opened directly in any browser — no server required."""
    os.makedirs(DESKTOP, exist_ok=True)

    data = _fetch_dashboard_data()
    html = _generate_html(data)

    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    return INDEX_HTML
