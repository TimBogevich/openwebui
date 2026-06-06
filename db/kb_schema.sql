-- ============================================================================
-- Knowledge-base vector store for the railway literature (RAG).
-- Idempotent — safe to re-run. Requires the pgvector extension (image
-- pgvector/pgvector:pg16). Embeddings are 1024-dim (multilingual-e5-large).
--
-- Populated by gcu/embed_kb.py from the curated context-forms in kb_out/.
-- Queried by the search_knowledge MCP tool (hybrid: vector + russian FTS).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS kb_chunks (
    id           BIGSERIAL PRIMARY KEY,
    collection   TEXT NOT NULL,                 -- 'pte' (нормативы) | 'textbooks' (учебники)
    source_file  TEXT NOT NULL,                 -- e.g. '1._ПТЭ-МЮ.md'
    breadcrumb   TEXT,                          -- «Книга > Глава > Раздел» (chunk context)
    citation     TEXT,                          -- «ПТЭ, разд. II, п.6» / «Зубков, разд. 1.1.1»
    content      TEXT NOT NULL,                 -- the chunk body (verbatim for ПТЭ)
    is_verbatim  BOOLEAN NOT NULL DEFAULT false,-- true for regulations (quote exactly)
    embedding    vector(1024),                  -- multilingual-e5-large
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('russian', coalesce(content,''))) STORED,
    source_hash  TEXT,                          -- per-source content hash (idempotent reload)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ANN index for cosine similarity (embeddings normalized → cosine ≈ best).
CREATE INDEX IF NOT EXISTS kb_chunks_embedding_idx
    ON kb_chunks USING hnsw (embedding vector_cosine_ops);

-- Russian full-text for the keyword half of hybrid search.
CREATE INDEX IF NOT EXISTS kb_chunks_tsv_idx
    ON kb_chunks USING gin (tsv);

CREATE INDEX IF NOT EXISTS kb_chunks_collection_idx ON kb_chunks (collection);
CREATE INDEX IF NOT EXISTS kb_chunks_source_idx     ON kb_chunks (source_file);

COMMENT ON TABLE kb_chunks IS
  'Справочная литература РЖД (ПТЭ + учебники), нарезанная на context-forms и '
  'векторизованная (multilingual-e5-large, 1024d). Гибридный поиск: '
  'embedding (HNSW cosine) + russian FTS (tsv). Источник цитирования — citation.';
