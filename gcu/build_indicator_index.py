# -*- coding: utf-8 -*-
"""Build/refresh indicator_index from metrics.

Embeds every distinct metrics.name once, stores alongside an example
indicator_number, section, unit, occurrence count, road-presence flag.
Idempotent: TRUNCATEs and rebuilds. Safe to re-run after loading new data.

Run inside gcu-mcp (has the embedding client + DB reach):
  docker exec gcu-mcp python3 /app/build_indicator_index.py
"""
import os, sys, json, urllib.request, psycopg

DB_URL  = os.environ.get("GCU_DATABASE_URL", "postgresql://postgres:Gcu2026!@gcu-postgres:5432/postgres")
EMB_URL = os.environ.get("KB_EMBED_URL",   "http://host.docker.internal:1234/v1/embeddings")
EMB_MODEL = os.environ.get("KB_EMBED_MODEL", "text-embedding-multilingual-e5-large-instruct")
# e5-large-instruct convention: passages bare, queries get the Instruct prefix.
# Indicator names are PASSAGES → no prefix here. find_indicator() will wrap the
# user query with the Instruct prefix on the query side.

def embed(texts):
    """Batch-embed via OpenAI-compatible /v1/embeddings."""
    req = urllib.request.Request(
        EMB_URL,
        data=json.dumps({"model": EMB_MODEL, "input": texts}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return [d["embedding"] for d in json.load(r)["data"]]

def main():
    print(f"[build] reading distinct names from metrics ...")
    conn = psycopg.connect(DB_URL)
    with conn.cursor() as cur:
        # Each name aggregated: example indicator_number, section, unit, count, road-flag
        cur.execute("""
            SELECT name,
                   (array_agg(indicator_number) FILTER (WHERE indicator_number IS NOT NULL))[1] AS ex_inum,
                   (array_agg(section_roman)    FILTER (WHERE section_roman    IS NOT NULL))[1] AS ex_section,
                   (array_agg(unit)             FILTER (WHERE unit             IS NOT NULL))[1] AS ex_unit,
                   count(*)                                AS n_occ,
                   bool_or(road IS NOT NULL)               AS has_road
            FROM metrics
            WHERE name IS NOT NULL AND length(trim(name)) > 0
            GROUP BY name
            ORDER BY n_occ DESC
        """)
        rows = cur.fetchall()
    print(f"[build] {len(rows)} distinct names to embed")

    # Embed in batches (e5 handles long batches but 50 is comfortable)
    BATCH = 50
    embeddings = []
    for i in range(0, len(rows), BATCH):
        batch_names = [r[0] for r in rows[i:i+BATCH]]
        print(f"  batch {i}-{i+len(batch_names)} ...", end=" ", flush=True)
        embeddings.extend(embed(batch_names))
        print("ok")
    assert len(embeddings) == len(rows), f"got {len(embeddings)} embeddings for {len(rows)} names"

    # Write
    with conn.cursor() as cur:
        cur.execute("TRUNCATE indicator_index")
        for (name, ex_inum, ex_section, ex_unit, n_occ, has_road), emb in zip(rows, embeddings):
            vec = "[" + ",".join(f"{x:.7g}" for x in emb) + "]"
            cur.execute(
                "INSERT INTO indicator_index "
                "(name, embedding, example_inum, example_section, example_unit, n_occurrences, has_road) "
                "VALUES (%s, %s::vector, %s, %s, %s, %s, %s)",
                (name, vec, ex_inum, ex_section, ex_unit, n_occ, has_road))
    conn.commit()
    print(f"[OK] indexed {len(rows)} names into indicator_index")
    conn.close()

if __name__ == "__main__":
    main()
