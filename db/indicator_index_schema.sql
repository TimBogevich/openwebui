-- ============================================================================
-- indicator_index — semantic index over distinct metrics.name values.
-- Lets find_indicator() return candidate names by MEANING instead of forcing
-- the model to fish via trigram. Source of truth: metrics table.
-- Idempotent. Rebuild after schema/data changes via gcu/build_indicator_index.py
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS indicator_index (
    name              varchar(512) PRIMARY KEY,
    embedding         vector(1024),
    example_inum      varchar(32),       -- a real indicator_number using this name
    example_section   varchar(8),        -- I/II/III…
    example_unit      varchar(64),       -- %, тыс. тонн, км/ч etc
    n_occurrences     int,               -- how many metric rows use this name
    has_road          boolean,           -- true if any row with this name has road != NULL
    indexed_at        timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_indicator_index_hnsw
    ON indicator_index USING hnsw (embedding vector_cosine_ops);

COMMENT ON TABLE indicator_index IS
  'Semantic search index over distinct metrics.name. Rebuild via build_indicator_index.py '
  'whenever new dates are loaded. Query via MCP tool find_indicator(text).';
