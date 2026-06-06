# -*- coding: utf-8 -*-
"""
Embed the curated knowledge-base context-forms (kb_out/*.md) into Postgres
(table kb_chunks, pgvector). Reads the markdown produced by prepare_kb.py,
splits it back into chunks on the «## breadcrumb» / «--- » boundaries, embeds
each via an OpenAI-compatible /v1/embeddings endpoint (LM Studio), and inserts.

IMPORTANT — e5 prefix convention (model-dependent, VERIFIED empirically):
  • multilingual-e5-large-INSTRUCT (what we use): passages embedded BARE (no
    prefix); the QUERY is wrapped with an instruction (see KB_QUERY_INSTRUCT in
    the search_knowledge tool). Best retrieval margin in our test → run with
    --no-prefix here.
  • plain multilingual-e5-large (non-instruct): "passage:" for docs, "query:"
    for the query. Drop --no-prefix.
  • nomic/bge: no prefixes → --no-prefix.
  The passage-side convention lives here; the query-side lives in the MCP tool.
  They MUST match the same embedding model.

Idempotent: each source file's rows are deleted+reinserted (by source_file).

Usage (inside a container that can reach Postgres + LM Studio):
    python embed_kb.py kb_out \
        --embed-url http://host.docker.internal:1234/v1/embeddings \
        --model text-embedding-multilingual-e5-large \
        --dim 1024

Env fallbacks: GCU_DATABASE_URL, EMBED_URL, EMBED_MODEL, EMBED_DIM.
"""
import os
import re
import sys
import glob
import json
import time
import hashlib
import argparse
import urllib.request


# --------------------------------------------------------------------------
# Parse a curated .md back into (breadcrumb, citation, body) chunks
# --------------------------------------------------------------------------
# source=... may contain spaces (e.g. «1. ПТЭ-МЮ.DOCX») — capture up to the
# next « key=» token, not just non-whitespace.
_HDR = re.compile(
    r"<!--\s*collection=(?P<coll>\S+)\s+source=(?P<src>.+?)\s+verbatim=(?P<verb>\S+)", re.I)
_SRC_CITE = re.compile(r"^_Источник:\s*(.+?)_\s*$", re.M)


def parse_md(path):
    """Return (collection, source, is_verbatim, [ (breadcrumb, citation, content) ])."""
    txt = open(path, encoding="utf-8").read()
    m = _HDR.search(txt)
    # collection: header value, else infer from the parent dir name (pte/textbooks)
    parent = os.path.basename(os.path.dirname(path))
    collection = m.group("coll") if m else (parent if parent in ("pte", "textbooks") else "textbooks")
    source = os.path.basename(path)                      # stable: the .md filename
    is_verbatim = (m.group("verb").lower() == "true") if m else (collection == "pte")

    chunks = []
    for block in txt.split("\n---\n"):
        block = block.strip()
        if not block or block.startswith("<!--"):
            block = re.sub(r"<!--.*?-->", "", block, flags=re.S).strip()
            if not block:
                continue
        # breadcrumb = first «## ...» line
        bm = re.search(r"^##\s+(.+)$", block, re.M)
        breadcrumb = bm.group(1).strip() if bm else None
        # citation = «_Источник: ..._»
        cm = _SRC_CITE.search(block)
        citation = cm.group(1).strip() if cm else (breadcrumb or source)
        # body = block minus the ## header, the «> О чём:» prefix, and the source line
        body = block
        if bm:
            body = body.replace(bm.group(0), "", 1)
        body = re.sub(r"^>\s*О чём:.*$", "", body, flags=re.M)
        body = _SRC_CITE.sub("", body).strip()
        if len(body) < 30:
            continue
        chunks.append((breadcrumb, citation, body))
    return collection, source, is_verbatim, chunks


# --------------------------------------------------------------------------
# Embedding via OpenAI-compatible endpoint
# --------------------------------------------------------------------------
def embed_batch(texts, url, model, prefix):
    payload = {"model": model, "input": [prefix + t for t in texts]}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    # keep API order
    return [d["embedding"] for d in sorted(data["data"], key=lambda x: x["index"])]


# --------------------------------------------------------------------------
# DB
# --------------------------------------------------------------------------
def connect(db_url):
    import psycopg
    return psycopg.connect(db_url, connect_timeout=10)


def vec_literal(v):
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="kb_out dir (or a single .md)")
    ap.add_argument("--db", default=os.environ.get(
        "GCU_DATABASE_URL", "postgresql://postgres:Gcu2026!@postgres:5432/postgres"))
    ap.add_argument("--embed-url", default=os.environ.get(
        "EMBED_URL", "http://host.docker.internal:1234/v1/embeddings"))
    ap.add_argument("--model", default=os.environ.get(
        "EMBED_MODEL", "text-embedding-multilingual-e5-large"))
    ap.add_argument("--dim", type=int, default=int(os.environ.get("EMBED_DIM", "1024")))
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--no-prefix", action="store_true",
                    help="disable e5 'passage:' prefix (for nomic/bge embedders)")
    args = ap.parse_args()

    prefix = "" if args.no_prefix else "passage: "
    files = ([args.src] if args.src.endswith(".md")
             else sorted(glob.glob(os.path.join(args.src, "**", "*.md"), recursive=True)))
    print(f"Embedding {len(files)} file(s) | model={args.model} dim={args.dim} prefix={prefix!r}")

    # sanity: one probe to confirm endpoint + dimension
    probe = embed_batch(["проверка"], args.embed_url, args.model, prefix)
    if len(probe[0]) != args.dim:
        print(f"FATAL: embedder returned dim {len(probe[0])}, expected {args.dim}. "
              f"Fix --dim or the vector({args.dim}) column.")
        sys.exit(2)
    print(f"  endpoint OK, dim={len(probe[0])}")

    conn = connect(args.db)
    conn.autocommit = False
    cur = conn.cursor()

    grand = 0
    for fp in files:
        collection, source, is_verbatim, chunks = parse_md(fp)
        if not chunks:
            print(f"  (skip empty) {os.path.basename(fp)}")
            continue
        src_hash = hashlib.sha1(open(fp, "rb").read()).hexdigest()[:16]
        # idempotent: replace this source's rows
        cur.execute("DELETE FROM kb_chunks WHERE source_file = %s", (source,))

        inserted = 0
        for i in range(0, len(chunks), args.batch):
            batch = chunks[i:i + args.batch]
            vecs = embed_batch([c[2] for c in batch], args.embed_url, args.model, prefix)
            for (breadcrumb, citation, body), vec in zip(batch, vecs):
                cur.execute(
                    "INSERT INTO kb_chunks "
                    "(collection, source_file, breadcrumb, citation, content, is_verbatim, embedding, source_hash) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s::vector,%s)",
                    (collection, source, breadcrumb, citation, body, is_verbatim,
                     vec_literal(vec), src_hash),
                )
                inserted += 1
            print(f"\r  [{collection}] {source}: {inserted}/{len(chunks)}", end="", flush=True)
        conn.commit()
        grand += inserted
        print(f"\r  [{collection}] {source}: {inserted} chunks embedded.        ")

    cur.execute("SELECT collection, count(*) FROM kb_chunks GROUP BY 1 ORDER BY 1")
    print("Totals:", cur.fetchall())
    conn.close()
    print(f"DONE. {grand} chunks embedded.")


if __name__ == "__main__":
    main()
