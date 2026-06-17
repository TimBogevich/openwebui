-- metrics_comments.sql — Russian COMMENT ON COLUMN для metrics + reports.
-- Применение: docker exec -i gcu-postgres psql -U postgres -d postgres < db/metrics_comments.sql

-- zone_label: декодированный код зоны в слово (генерируемая колонка).
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS zone_label text
  GENERATED ALWAYS AS (CASE zone WHEN 0 THEN 'зелёная' WHEN 1 THEN 'жёлтая' WHEN 2 THEN 'красная' WHEN 4 THEN 'особая' END) STORED;

COMMENT ON COLUMN metrics.zone IS 'Числовой код зоны риска: 0 = зелёная, 1 = жёлтая, 2 = красная, 4 = особая (информационная).zone_label содержит то же значение словом.';
COMMENT ON COLUMN metrics.zone_label IS 'Зона риска словом: зелёная / жёлтая / красная / особая. zone_label = zone, но уже в текстовой форме.';
COMMENT ON COLUMN metrics.day_to_plan IS 'Отклонение факта за сутки от плана. При unit=% значение в процентных пунктах; иначе — доля.';
COMMENT ON COLUMN metrics.day_to_prev_year IS 'Отклонение за сутки к прошлому году. Единица та же, что у day_to_plan.';
COMMENT ON COLUMN metrics.month_to_plan IS 'Отклонение нарастающим итогом за месяц от плана. Единица та же, что у day_to_plan.';
COMMENT ON COLUMN metrics.month_to_prev_yr IS 'Отклонение за месяц к прошлому году. Единица та же, что у day_to_prev_year.';
COMMENT ON COLUMN metrics.year_to_plan IS 'Отклонение нарастающим итогом за год от плана. Единица та же, что у day_to_plan.';
COMMENT ON COLUMN metrics.year_to_prev_yr IS 'Отклонение за год к прошлому году. Единица та же, что у day_to_prev_year.';
COMMENT ON COLUMN metrics.day_fact IS 'Факт за сутки.';
COMMENT ON COLUMN metrics.month_fact IS 'Факт нарастающим итогом с начала месяца.';
COMMENT ON COLUMN metrics.year_fact IS 'Факт нарастающим итогом с начала года.';
COMMENT ON COLUMN metrics.populates IS 'Какой период заполнен у показателя: суточный / месячный / годовой / смешанный / нет.';
COMMENT ON COLUMN metrics.road IS 'Название дороги для строк с разбивкой по дорогам; пусто для строк без дороги.';
COMMENT ON COLUMN metrics.responsible IS 'Ответственное подразделение (ЦД, ЦТ, ЦДИ, ЦФТО …); расшифровка в dept_codes.';
COMMENT ON COLUMN metrics.parent_indicator IS 'Номер родительского показателя (пример: ''7.7.3.3'' для ''7.7.3.3.1'').';
COMMENT ON COLUMN metrics.unit IS 'Единица измерения: %, км/ч, тыс. тонн, ед. …';

-- reports
COMMENT ON COLUMN reports.baseline_year IS 'Год сравнения для отклонений к прошлому году: март 2022 → 2021; апрель 2026 → 2025.';
COMMENT ON COLUMN reports.report_date IS 'Дата доклада. Одна строка reports на один xlsx-файл.';

-- Таблицы
COMMENT ON TABLE reports IS 'Ежедневный доклад ЦГЦУ.';
COMMENT ON TABLE metrics IS 'Оперативные показатели из листов «Доклад Ц ЦЗ» и «Срок доставки». report_date — в таблице reports, связь по report_id.';
