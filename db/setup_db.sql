-- ============================================================================
-- One-shot DB setup — run AFTER restoring db/gtsu_search_dump.sql into a fresh
-- Postgres volume. Applies column-comment semantics + decoded views (gtsu,
-- gtsu_catalog). These live in the postgres volume, so re-apply on rebuild.
--   docker exec -i gcu-postgres psql -U postgres -d postgres < db/setup_db.sql
-- Idempotent (COMMENT / CREATE OR REPLACE VIEW are safe to re-run).
-- ============================================================================

-- ---- column comments (semantics surfaced by the describe tool) ----
COMMENT ON TABLE gtsu_search IS 'Ежедневный Доклад ГЦУ ОАО РЖД — плоская иерархическая витрина показателей.';
COMMENT ON COLUMN gtsu_search.report_date IS 'Дата доклада ГЦУ.';
COMMENT ON COLUMN gtsu_search.section_code IS 'Код раздела доклада (I, II, III...).';
COMMENT ON COLUMN gtsu_search.section_title IS 'Название раздела доклада.';
COMMENT ON COLUMN gtsu_search.sheet_name IS 'Имя листа исходного Excel.';
COMMENT ON COLUMN gtsu_search.item_number IS 'Иерархический номер показателя (напр. 1, 1.1, 1.1.7).';
COMMENT ON COLUMN gtsu_search.item_depth IS 'Глубина в дереве показателей (1=раздел, 3=лист).';
COMMENT ON COLUMN gtsu_search.parent_path IS 'Путь по родительским разделам дерева (через '' > ''). Здесь лежит ТЕМА/категория показателя.';
COMMENT ON COLUMN gtsu_search.indicator IS 'Название ИМЕННО этой строки — лист дерева. У детализированных строк это конкретный объект (напр. название железной дороги), а НЕ тема.';
COMMENT ON COLUMN gtsu_search.full_indicator IS 'parent_path + '' > '' + indicator. Используйте для поиска по теме (ILIKE), т.к. объединяет категорию и лист.';
COMMENT ON COLUMN gtsu_search.unit IS 'Единица измерения.';
COMMENT ON COLUMN gtsu_search.responsible IS 'Ответственное подразделение (ЦД, ЦТ, ЦФТО...).';
COMMENT ON COLUMN gtsu_search.color_marker IS 'Зона показателя (цвет в докладе): 2=КРАСНАЯ (критично), 1=ЖЁЛТАЯ (внимание), 0=ЗЕЛЁНАЯ (норма), 4=особая/информационная (без порога; справочные строки), NULL=без зоны. Для «красной зоны» фильтруй WHERE color_marker=2.';
COMMENT ON COLUMN gtsu_search.metrics IS 'JSONB с числами. Ключи (используй ТОЧНО эти русские имена, англ. ключей НЕТ): факт_сутки, сутки_к_плану, сутки_к_2021, факт_месяц, месяц_к_плану, месяц_к_2021, факт_год, год_к_плану, год_к_2021. Для раздела III (инвест): ввод_фондов_* и инвест_затраты_* (план_периода, прогноз, утв_план_года, проц_к_плану_года, проц_к_плану_периода). Извлекай как (metrics->>''ключ'')::numeric со скобками. Отклонения *_к_плану и *_к_2021 — ДОЛИ (-0.0979 = -9.79%).';
COMMENT ON COLUMN gtsu_search.text_comment IS 'Текстовый комментарий из доклада.';
COMMENT ON COLUMN gtsu_search.management_actions IS 'Предлагаемые управленческие решения.';
COMMENT ON COLUMN gtsu_search.narrative IS 'Человекочитаемый абзац (для полнотекстового поиска).';
COMMENT ON COLUMN gtsu_search.source_row IS 'Номер строки в исходном Excel.';

-- ---- decoded views ----
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
