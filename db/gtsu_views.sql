-- ============================================================================
-- Decoded views over gtsu_search (the flat JSONB витрина) so the model writes
-- simple, correct SQL instead of fumbling JSONB casts / inventing table names.
--
-- Built AFTER fact-checking the real demo dump (2026-06-04), which CORRECTED
-- the external review's S3 in two ways:
--   1) The «Доработка системы-источника» rows are NOT all junk — 496 of 527 are
--      the REAL per-road speed children (indicator=дорога). Only the 31 depth<3
--      PARENT aggregates are empty. So we DO NOT drop by name; we keep children.
--   2) факт_месяц / факт_год are «нарастающим итогом» but for RATE metrics
--      (км/сут, ткм/сут) that is a running AVERAGE-to-date, NOT a sum. Labelled
--      as «_нараст» (значение с начала периода), never «сумма».
-- ============================================================================

-- 1) gtsu — typed, decoded, analysis-friendly view. Real columns, % as numbers,
--    zone as text, period made explicit. Numeric casts done once, safely.
CREATE OR REPLACE VIEW gtsu AS
SELECT
  report_date,
  section_code,
  section_title,
  item_number,
  item_depth,
  parent_path,
  indicator,                                  -- лист дерева (часто = объект: дорога, класс…)
  full_indicator,                             -- parent_path > indicator (для поиска по теме)
  unit,
  responsible,                                -- ответственное подразделение (ЦД, ЦТ…), НЕ дорога
  CASE color_marker
       WHEN 2 THEN 'красная' WHEN 1 THEN 'жёлтая' WHEN 0 THEN 'зелёная'
       WHEN 4 THEN 'особая'  ELSE NULL END                       AS зона,
  color_marker,
  -- за сутки (ДНЕВНОЕ значение этой даты)
  (metrics->>'факт_сутки')::numeric                              AS факт_сутки,
  round((metrics->>'сутки_к_плану')::numeric * 100, 2)           AS откл_сутки_план_pct,
  round((metrics->>'сутки_к_2021')::numeric * 100, 2)            AS откл_сутки_2021_pct,
  -- с начала месяца (нарастающим итогом; для ставок/скоростей — среднее-к-дате)
  (metrics->>'факт_месяц')::numeric                              AS факт_месяц_нараст,
  round((metrics->>'месяц_к_плану')::numeric * 100, 2)           AS откл_месяц_план_pct,
  round((metrics->>'месяц_к_2021')::numeric * 100, 2)            AS откл_месяц_2021_pct,
  -- с начала года (нарастающим итогом)
  (metrics->>'факт_год')::numeric                                AS факт_год_нараст,
  round((metrics->>'год_к_плану')::numeric * 100, 2)             AS откл_год_план_pct,
  round((metrics->>'год_к_2021')::numeric * 100, 2)              AS откл_год_2021_pct,
  text_comment,
  management_actions,
  metrics                                     -- сырой JSONB оставлен для инвест-ключей (разд. III)
FROM gtsu_search;

COMMENT ON VIEW gtsu IS
  'Декодированная витрина над gtsu_search: типизированные колонки, отклонения уже в процентах (*_pct), зона текстом. факт_месяц_нараст/факт_год_нараст — нарастающим итогом (для ставок и скоростей — среднее с начала периода, НЕ сумма). факт_сутки — за день. Используй ЭТУ view для числовых вопросов вместо разбора JSONB.';

-- 2) gtsu_catalog — «что есть в данных»: справочник показателей/разрезов.
--    Помогает модели не отвечать по памяти на «есть ли разбивка по X».
CREATE OR REPLACE VIEW gtsu_catalog AS
SELECT DISTINCT
  section_title, item_number, item_depth, parent_path, indicator,
  full_indicator, unit, responsible
FROM gtsu_search
ORDER BY section_title, item_number;

COMMENT ON VIEW gtsu_catalog IS
  'Каталог показателей и их разрезов (уникальные строки витрины). Смотри здесь, чтобы узнать какие показатели и какая детализация (по дорогам/филиалам) реально есть, прежде чем отвечать.';
