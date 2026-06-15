-- ============================================================================
-- ЦГЦУ analyst app — schema v2 (typed columns, no JSONB on metrics).
-- Replaces the legacy gtsu_search JSONB prototype. Idempotent.
--
-- Cleanup 2026-06-06: dropped dead degrees of freedom (subcategory, raw_data,
-- audit_log, reports.status/error_message — all were 0% used after a full
-- 61-day load). Promoted source_sheet/source_row to typed columns. Added
-- metrics.populates so callers can filter cumulative-only indicators
-- explicitly instead of guessing on NULL day_fact.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;     -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;       -- already used by kb_chunks

-- ---------------------------------------------------------------------------
-- reports — one row per ingested xlsx file
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reports (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    filename        varchar(512) NOT NULL,
    report_date     date NOT NULL,
    baseline_year   int2,                                -- year that '*_to_prev_year' compares to
    sha256          varchar(64) NOT NULL,
    sheets_count    int4,
    metrics_count   int4,
    red_count       int4,
    yellow_count    int4,
    green_count     int4,
    file_path       varchar(1024),
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reports_date    ON reports (report_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_sha256 ON reports (sha256);

-- ---------------------------------------------------------------------------
-- report_sheets — one row per sheet inside a report
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_sheets (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    report_id       uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    sheet_name      varchar(256) NOT NULL,
    sheet_index     int4 NOT NULL,
    row_count       int4,
    col_count       int4,
    has_text_cols   bool DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_sheets_report ON report_sheets (report_id);

-- ---------------------------------------------------------------------------
-- metrics — one row per indicator leaf, OPERATIONAL sheets only
--   (Доклад Ц ЦЗ + Срок доставки). Investment goes to investment_metrics.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metrics (
    id                  uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    report_id           uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    sheet_id            uuid REFERENCES report_sheets(id),
    indicator_number    varchar(255),             -- "1.1.7"
    parent_indicator    varchar(255),             -- immediate parent of indicator_number ("1.1" for "1.1.7"; "7.7.3.3" for "7.7.3.3.1")
    is_priority         bool DEFAULT false,       -- column C "*" flag
    section_roman       varchar(16),              -- "I", "II"
    name                varchar(512) NOT NULL,    -- the indicator label
    category            varchar(256),             -- top-level theme (e.g. "1. ГРУЗОВЫЕ ПЕРЕВОЗКИ")
    road                varchar(64),              -- railway name for per-road rows (Октябрьская…); NULL otherwise
    unit                varchar(64),
    responsible         varchar(64),              -- ЦД, ЦТ, ЦФТО…
    zone                int2 DEFAULT 0,           -- 0=green, 1=yellow, 2=red, 4=special
    -- Typed numeric values. Deviations are stored as FRACTIONS (-0.0979 = -9.79%).
    day_fact            float8,
    day_to_plan         float8,
    day_to_prev_year    float8,
    month_fact          float8,
    month_to_plan       float8,
    month_to_prev_yr    float8,
    year_fact           float8,
    year_to_plan        float8,
    year_to_prev_yr     float8,
    -- Which period the indicator actually populates ('daily' | 'monthly' | 'yearly' | 'mixed' | 'none').
    -- Counters/итоги (опоздания, поставки, происшествия…) often leave day_fact NULL — use this
    -- column to filter explicitly rather than guessing on NULL.
    populates           varchar(8),
    -- Source traceability (was JSONB metadata; now typed)
    cell_ref            varchar(32),              -- "B14"
    source_sheet        varchar(256),             -- "Доклад Ц ЦЗ"
    source_row          int4,
    created_at          timestamptz DEFAULT now(),
    CONSTRAINT metrics_zone_check CHECK (zone IS NULL OR zone IN (0,1,2,4)),
    CONSTRAINT metrics_populates_check CHECK (populates IS NULL OR populates IN ('daily','monthly','yearly','mixed','none'))
);
CREATE INDEX IF NOT EXISTS idx_metrics_report           ON metrics (report_id);
CREATE INDEX IF NOT EXISTS idx_metrics_zone             ON metrics (zone);
CREATE INDEX IF NOT EXISTS idx_metrics_indicator_number ON metrics (indicator_number);
CREATE INDEX IF NOT EXISTS idx_metrics_parent           ON metrics (parent_indicator);
CREATE INDEX IF NOT EXISTS idx_metrics_responsible      ON metrics (responsible);
CREATE INDEX IF NOT EXISTS idx_metrics_road             ON metrics (road) WHERE road IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_metrics_category         ON metrics (category);
CREATE INDEX IF NOT EXISTS idx_metrics_populates        ON metrics (populates);
-- Partial index: the "red/yellow on date X" query goes index-only.
CREATE INDEX IF NOT EXISTS idx_metrics_problem
    ON metrics (report_id, zone) WHERE zone IN (1,2);
-- Russian FTS on the indicator name.
CREATE INDEX IF NOT EXISTS idx_metrics_name_search
    ON metrics USING gin (to_tsvector('russian', name));
-- Trigram index → fuzzy name search (`name % 'запрос'`, ORDER BY similarity(...)).
-- Needed because indicator names are heavily ABBREVIATED in the source («груз.»,
-- «в т.ч.», «установл.») and an ILIKE on a guessed full word misses.
CREATE INDEX IF NOT EXISTS idx_metrics_name_trgm
    ON metrics USING gin (name gin_trgm_ops);

-- ---------------------------------------------------------------------------
-- investment_metrics — Инвест + Инвест Факт sheets (different shape)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS investment_metrics (
    id                              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    report_id                       uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    sheet_id                        uuid REFERENCES report_sheets(id),
    code_spiui                      varchar(64),              -- "5.01.02.03"
    federal_project                 varchar(256),
    section_roman                   varchar(16),
    parent_indicator                varchar(255),
    program                         varchar(512) NOT NULL,    -- "5 Инвестиционная программа …"
    is_forecast                     bool,                     -- "Инвест" → true; "Инвест Факт" → false
    zone                            int2,
    -- Investment expenses
    exp_approved_year               float8,                   -- утв. план года
    exp_period_plan                 float8,                   -- план периода
    exp_fact_or_forecast            float8,                   -- факт OR прогноз (see is_forecast)
    exp_pct_to_period               float8,
    exp_pct_to_year                 float8,
    -- Fixed-assets commissioning
    funds_approved_year             float8,
    funds_period_plan               float8,
    funds_fact_or_forecast          float8,
    funds_pct_to_period             float8,
    funds_pct_to_year               float8,
    cell_ref                        varchar(32),
    source_sheet                    varchar(256),
    source_row                      int4,
    created_at                      timestamptz DEFAULT now(),
    CONSTRAINT inv_zone_check CHECK (zone IS NULL OR zone IN (0,1,2,4))
);
CREATE INDEX IF NOT EXISTS idx_inv_report      ON investment_metrics (report_id);
CREATE INDEX IF NOT EXISTS idx_inv_code        ON investment_metrics (code_spiui);
CREATE INDEX IF NOT EXISTS idx_inv_forecast    ON investment_metrics (is_forecast);

-- ---------------------------------------------------------------------------
-- report_comments — textual commentary + management actions, separated
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_comments (
    id                  uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    report_id           uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    metric_id           uuid REFERENCES metrics(id),
    sheet_id            uuid REFERENCES report_sheets(id),
    indicator_number    varchar(255),
    commentary          text,
    management_action   text,
    row_index           int4 NOT NULL,
    created_at          timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_comments_report ON report_comments (report_id);
CREATE INDEX IF NOT EXISTS idx_comments_metric ON report_comments (metric_id);
-- Russian FTS over comment + action.
CREATE INDEX IF NOT EXISTS idx_comments_text_search
    ON report_comments USING gin (to_tsvector('russian',
        coalesce(commentary,'') || ' ' || coalesce(management_action,'')));

-- ---------------------------------------------------------------------------
-- Column-level documentation surfaced by describe()
-- ---------------------------------------------------------------------------
-- NOTE: full Russian column/table comments live in db/metrics_comments.sql
-- (single source of truth, surfaced by describe()). The lines below are kept in
-- sync so a fresh schema apply doesn't reintroduce English.
COMMENT ON TABLE  reports             IS 'Ежедневный доклад ЦГЦУ (одна строка на xlsx-файл). baseline_year — год сравнения для столбцов отклонения к прошлому году.';
COMMENT ON TABLE  metrics             IS 'Оперативные показатели докладов ЦГЦУ (листы «Доклад Ц ЦЗ» и «Срок доставки»). Все числа в типизированных колонках. report_date — в таблице reports, связь по report_id.';
COMMENT ON TABLE  investment_metrics  IS 'Инвестиционная программа (листы «Инвест» и «Инвест Факт»). 10 типизированных колонок: расходы и ввод фондов × {утв./план периода/факт/% к периоду/% к году}.';
COMMENT ON TABLE  report_comments     IS 'Текстовые комментарии и управленческие действия, отдельно от metrics (у одного показателя может быть несколько).';
COMMENT ON COLUMN metrics.zone        IS 'Зона риска показателя: 0 = зелёная (норма), 1 = жёлтая, 2 = красная (критическая), 4 = особая (информационная).';
COMMENT ON COLUMN metrics.day_to_plan IS 'Отклонение факта за сутки от плана. При unit=''%'' значение уже в процентных пунктах (0,335 = +0,335 п.п.); иначе это доля (-0,0979 = -9,79%).';
COMMENT ON COLUMN metrics.road        IS 'Название дороги для строк разбивки по дорогам; пусто для строк не по дорогам.';
COMMENT ON COLUMN metrics.populates   IS 'Период, который реально заполнен у показателя: суточный / месячный / годовой / смешанный / нет.';
COMMENT ON COLUMN metrics.parent_indicator IS 'Номер родительского показателя в дереве (например ''7.7.3.3'' для ''7.7.3.3.1'').';
COMMENT ON COLUMN reports.baseline_year IS 'Год сравнения для отклонений к прошлому году: март 2022 → 2021; апрель 2026 → 2025.';
