-- views_loco_speedrestr.sql — pre-computed views for the two questions the model
-- kept botching even with COMMENT guidance (Q6 ограничения, Q7 локомотивы).
-- Follows the existing v_delays_total / v_ports_network pattern: collapse the
-- error-prone multi-row aggregation/JOIN into one clean queryable shape so the
-- model can't (a) pick *_total instead of gruzovoe, or (b) sum plan+fact rows.
--
-- Apply:
--   docker exec -i gcu-postgres psql -U postgres -d postgres < db/views_loco_speedrestr.sql

-- ── Q7: locomotive deficit in FREIGHT movement, by traction type ────────────
-- Network row (polygon IS NULL) per section, gruzovoe columns only (plan/fact/
-- delta — NOT *_total). Excludes the Резерв pseudo-roads. One row per
-- (date, traction). Verified network deltas: AC -113, DC +48, diesel -65.
CREATE OR REPLACE VIEW v_locomotives_traction AS
SELECT
    report_date,
    section AS traction,            -- AC=электровозы перем. тока, DC=пост. тока, diesel=тепловозы
    SUM(plan)  AS plan,
    SUM(fact)  AS fact,
    SUM(delta) AS delta             -- <0 = недосодержание в грузовом движении
FROM spravki_locomotives
WHERE polygon IS NULL              -- polygon-total rows (road = polygon name)
  AND road NOT ILIKE '%езерв%'     -- drop Резерв pseudo-rows
GROUP BY report_date, section;

COMMENT ON VIEW v_locomotives_traction IS
  'Предвычисленное недосодержание эксплуатируемого парка локомотивов в ГРУЗОВОМ '
  'движении по сети, в разрезе типов тяги. traction: AC=электровозы переменного '
  'тока, DC=электровозы постоянного тока, diesel=тепловозы. plan/fact/delta — '
  'грузовое движение (delta<0 = недосодержание). Один ряд на (дата, тип тяги). '
  'Для вопроса «содержание/недосодержание парка локомотивов» бери ЭТОТ вид — он '
  'уже исключает *_total (весь парк с резервом) и резервные строки. '
  'ИСТОЧНИК ДЛЯ ОТВЕТА: АРМ ОНД — Справка Локомотивы. '
  'ОТВЕТ: перечисли все три типа тяги с их delta; НЕ суммируй в одно число.';

-- ── Q6: speed restrictions — fact + plan level per road ─────────────────────
-- Joins the latest fact rows to the plan rows (which carry ratio_pct = уровень,
-- доля факта от плана, %). One row per road. Lets the model rank by level_pct
-- (>100 = нарушитель) without summing plan+fact rows (the bug that produced the
-- hallucinated 3786/2335 doubling).
CREATE OR REPLACE VIEW v_speed_restrictions AS
SELECT
    f.report_date,
    f.road,
    f.restrictions      AS restrictions,      -- фактическое количество, ед.
    f.restrictions_km   AS restrictions_km,   -- фактическая протяжённость, км
    p.ratio_pct         AS level_pct,         -- уровень = доля факта от плана, %; >100 = превышение
    p.delta_km          AS delta_km           -- изменение протяжённости к прошлому периоду
FROM spravki_speed_restrictions f
LEFT JOIN spravki_speed_restrictions p
       ON p.road = f.road AND p.row_type = 'plan'
WHERE f.row_type = 'fact'
  AND f.report_date = (SELECT max(report_date) FROM spravki_speed_restrictions WHERE row_type='fact');

COMMENT ON VIEW v_speed_restrictions IS
  'Предвычисленные ограничения скорости по дорогам: факт (restrictions ед., '
  'restrictions_km км) + плановый уровень level_pct (доля факта от плана, %; '
  '>100 = превышение планового уровня = дорога-нарушитель). Один ряд на дорогу '
  '(строка road=''Итого по сети'' — сетевой итог). Берёт ТОЛЬКО последнюю дату '
  'факта и НЕ суммирует строки plan+fact (иначе задвоение). '
  'ИСТОЧНИК ДЛЯ ОТВЕТА: АСУ ВОП-2 — Справка об ограничениях скорости, не '
  'предусмотренных графиком движения поездов. '
  'ОТВЕТ: сначала дороги с level_pct>100 (Горьковская 189%, Северо-Кавказская '
  '103%) — основные нарушители; затем по протяжённости restrictions_km. Дорогу с '
  'большим километражом, но level_pct<=100 (Свердловская 257 км, уровень 87%), не '
  'ставь первой — план не превышен.';
