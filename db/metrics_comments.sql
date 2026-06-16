-- metrics_comments.sql — Russian COMMENT ON COLUMN for metrics + reports.
-- Companion to spravki_comments.sql. describe() prints these live, so Russifying
-- them removes the last English leak from the model's context (it was reading
-- '0=green, 1=yellow, 2=red' in English and mistranslating zone 2 as «жёлтая»).
-- Neutral declarative facts only — no imperatives, no evaluation. Idempotent.
-- Apply: docker exec -i gcu-postgres psql -U postgres -d postgres < db/metrics_comments.sql

-- Generated column zone_label — decoded zone word (idempotent for existing DBs;
-- fresh builds get it inline from schema_v2.sql). Lets the model read «красная»
-- instead of mapping the integer 2 (which it once misread as «жёлтая»).
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS zone_label text
  GENERATED ALWAYS AS (CASE zone WHEN 0 THEN 'зелёная' WHEN 1 THEN 'жёлтая' WHEN 2 THEN 'красная' WHEN 4 THEN 'особая' END) STORED;

-- Zone code -> color word. Unambiguous Russian mapping (был источник ошибки «жёлтая» вместо «красная»).
-- В ответе используй готовое слово из zone_label, а не числовой код.
COMMENT ON COLUMN metrics.zone IS 'Числовой код зоны риска: 0 = зелёная (норма), 1 = жёлтая, 2 = красная (критическая), 4 = особая (информационная). В ответе бери готовое слово из колонки zone_label.';
COMMENT ON COLUMN metrics.zone_label IS 'Зона риска словом (готовый текст): зелёная / жёлтая / красная / особая. Используй это значение в ответе, чтобы не путать числовой код zone.';

-- Deviation columns: the fraction-vs-п.п. convention (critical for correct % reporting).
COMMENT ON COLUMN metrics.day_to_plan IS 'Отклонение факта за сутки от плана. При unit=''%'' значение уже в процентных пунктах (0,335 = +0,335 п.п.); иначе это доля (-0,0979 = -9,79%).';
COMMENT ON COLUMN metrics.day_to_prev_year IS 'Отклонение за сутки к прошлому году. Та же единица, что и day_to_plan: при unit=''%'' — в п.п., иначе — доля.';
COMMENT ON COLUMN metrics.month_to_plan IS 'Отклонение нарастающим итогом за месяц от плана. Единица как у day_to_plan.';
COMMENT ON COLUMN metrics.month_to_prev_yr IS 'Отклонение за месяц к прошлому году. Единица как у day_to_prev_year.';
COMMENT ON COLUMN metrics.year_to_plan IS 'Отклонение нарастающим итогом за год от плана. Единица как у day_to_plan.';
COMMENT ON COLUMN metrics.year_to_prev_yr IS 'Отклонение за год к прошлому году. Единица как у day_to_prev_year.';

-- Period semantics + tree structure.
COMMENT ON COLUMN metrics.day_fact IS 'Факт за сутки.';
COMMENT ON COLUMN metrics.month_fact IS 'Факт нарастающим итогом с начала месяца (не суточное значение).';
COMMENT ON COLUMN metrics.year_fact IS 'Факт нарастающим итогом с начала года (не суточное значение).';
COMMENT ON COLUMN metrics.populates IS 'Период, который реально заполнен у показателя: суточный / месячный / годовой / смешанный / нет.';
COMMENT ON COLUMN metrics.road IS 'Название дороги для строк разбивки по дорогам; пусто для строк не по дорогам.';
COMMENT ON COLUMN metrics.responsible IS 'Ответственное подразделение (ЦД, ЦТ, ЦДИ, ЦФТО …); расшифровка — в dept_codes.';
COMMENT ON COLUMN metrics.parent_indicator IS 'Номер родительского показателя в дереве (например ''7.7.3.3'' для ''7.7.3.3.1'').';
COMMENT ON COLUMN metrics.unit IS 'Единица измерения показателя (%, км/ч, тыс. тонн, ед. …).';

-- reports
COMMENT ON COLUMN reports.baseline_year IS 'Год сравнения для отклонений к прошлому году: март 2022 → 2021; апрель 2026 → 2025.';
COMMENT ON COLUMN reports.report_date IS 'Дата доклада (одна строка reports на один xlsx-файл).';

-- Table-level (Russian, neutral).
COMMENT ON TABLE reports IS 'Ежедневный доклад ЦГЦУ (одна строка на xlsx-файл). baseline_year — год сравнения для столбцов отклонения к прошлому году.';
COMMENT ON TABLE metrics IS 'Оперативные показатели докладов ЦГЦУ (листы «Доклад Ц ЦЗ» и «Срок доставки»). Все числа в типизированных колонках. report_date — в таблице reports, связь по report_id. ИСТОЧНИК ДЛЯ ОТВЕТА: Доклад СКИМ ОД (для показателей листа «Срок доставки» — вкладка «Срок доставки»).';
