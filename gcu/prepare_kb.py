# -*- coding: utf-8 -*-
"""
Stage-0 knowledge-base preparation — turn raw railway literature (PDF/DOCX) into
clean, self-contained "context-forms" (markdown) optimized for AI retrieval.

WHY: dumping raw PDFs into a vector store produces fragmented, noisy chunks
(mid-sentence splits, page-number garbage, broken hyphenation) that degrade the
model. This pass reads each book, DENOISES it, segments on REAL structure
(Roman sections + numbered clauses for ПТЭ; numbered headings for textbooks),
and emits one markdown block per coherent unit with a breadcrumb header and a
source citation. Those curated .md files are what get embedded later.

DOMAIN RULE:
  • Regulations (ПТЭ + приложения) → VERBATIM. Never rewrite legal/safety text.
  • Textbooks → cleaned text + a short context prefix (faithful body kept).

Output: kb_out/<collection>/<source-stem>.md  (reviewable on disk before ingest)

Usage:
    python prepare_kb.py <file-or-dir> [--collection pte|textbooks] [--out kb_out]
    # collection auto-detected if omitted (ПТЭ/ИДП/приложение → pte)

Pure stdlib + pypdf + python-docx-free DOCX reader (zipfile). No cloud, no model.
"""
import os
import re
import sys
import html
import glob
import zipfile
import hashlib
import argparse

# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------
def extract_docx(path):
    """Return list of non-empty paragraph strings from a .docx (no deps)."""
    z = zipfile.ZipFile(path)
    xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)          # paragraph -> newline
    xml = re.sub(r"<w:tab[^>]*>", "\t", xml)
    txt = html.unescape(re.sub(r"<[^>]+>", "", xml))
    return [ln.rstrip() for ln in txt.split("\n")]


def extract_pdf(path):
    """Return list of text lines from a PDF (pypdf), page by page."""
    from pypdf import PdfReader
    r = PdfReader(path)
    lines = []
    for pg in r.pages:
        t = pg.extract_text() or ""
        lines.extend(t.split("\n"))
    return lines


# --------------------------------------------------------------------------
# Denoise — the "better AI reading" cleanup
# --------------------------------------------------------------------------
_PAGENUM = re.compile(r"^\s*\d{1,4}\s*$")                 # lone page number line
# hyphenation: «слово-\nслово», incl. OCR variant with spaces «сло во- / ва ние»
_HYPHEN_EOL = re.compile(r"(\w)\s*-\s*$")
_MULTISPACE = re.compile(r"[ \t ]+")


def denoise(lines):
    """Strip page numbers / empty noise, repair end-of-line hyphenation, fold
    whitespace. Returns a single cleaned text string."""
    kept = []
    for ln in lines:
        s = ln.replace("\xa0", " ").strip()
        if not s:
            kept.append("")            # keep paragraph breaks
            continue
        if _PAGENUM.match(s):
            continue                   # drop floating page numbers
        kept.append(s)

    # join, repairing hyphen-at-EOL by gluing to the next line's first token
    out, i = [], 0
    while i < len(kept):
        cur = kept[i]
        m = _HYPHEN_EOL.search(cur)
        if m and i + 1 < len(kept) and kept[i + 1]:
            nxt = kept[i + 1].lstrip()
            cur = cur[: m.start(1) + 1] + nxt          # drop hyphen, glue
            kept[i + 1] = ""                            # consumed
            kept[i] = cur
            continue                                    # re-check same line
        out.append(cur)
        i += 1

    text = "\n".join(out)
    text = _MULTISPACE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------
# Segmentation
# --------------------------------------------------------------------------
# ПТЭ: Roman section «II. …», numbered clause «6. …» (nbsp already folded)
_ROMAN = re.compile(r"^([IVXLC]+)\.\s+(.+)$")
_CLAUSE = re.compile(r"^(\d{1,3})\.\s+(\S.+)$")
# Textbook headings, two accepted forms:
#  (a) DOTTED number  «1.2 …», «1.2.1 …»  — sentence-case title ok
#  (b) SINGLE int + ALL-CAPS title  «1 ПОСТРОЕНИЕ ПРОЦЕССНЫХ МОДЕЛЕЙ» — top-level
#      chapter. ALL-CAPS is the signal that distinguishes a chapter heading from
#      an ordinary list item like «1. Цель …» (sentence case → NOT a heading).
# Bare single-int + sentence-case is intentionally NOT matched (avoids false hits).
_HEADING_DOTTED = re.compile(r"^(\d+(?:\.\d+){1,3})\.?\s+([А-ЯЁ][^.;:]{3,80})\s*$")
_HEADING_CAPS = re.compile(r"^(\d{1,2})\.?\s+([А-ЯЁ][А-ЯЁ \-,]{6,80})\s*$")


def _match_heading(s):
    m = _HEADING_DOTTED.match(s)
    if m:
        return m.group(1), m.group(2).strip()
    m = _HEADING_CAPS.match(s)
    if m:
        # require it to be genuinely caps-heavy (≥80% uppercase letters)
        title = m.group(2).strip()
        letters = [c for c in title if c.isalpha()]
        if letters and sum(c.isupper() for c in letters) / len(letters) >= 0.8:
            return m.group(1), title
    return None


def segment_regulation(text, book):
    """ПТЭ-style: one segment per numbered clause, under its Roman section.
    VERBATIM bodies."""
    segs, section = [], None
    cur_no, cur_title, buf = None, None, []

    def flush():
        if cur_no and buf:
            body = "\n".join(buf).strip()
            crumb = f"{book} > {section} > п. {cur_no}" if section else f"{book} > п. {cur_no}"
            cite = f"{book}, {section}, п. {cur_no}" if section else f"{book}, п. {cur_no}"
            segs.append((crumb, cite, (cur_title + "\n" + body).strip()))

    for ln in text.split("\n"):
        s = ln.strip()
        mr = _ROMAN.match(s)
        mc = _CLAUSE.match(s)
        if mr and len(s) < 120:                 # section header
            flush(); cur_no, buf = None, []
            section = f"разд. {mr.group(1)} ({mr.group(2).strip()})"
            continue
        if mc:                                   # new clause
            flush()
            cur_no = mc.group(1); cur_title = mc.group(2).strip(); buf = []
            continue
        if s:
            buf.append(s)
    flush()

    # No-loss fallback for short annexes/forms with no numbered clauses.
    if not segs and text.strip():
        body = text.strip()
        if len(body) > 60:
            crumb = f"{book} > (полный текст)"
            segs.append((crumb, book, body))
    return segs


def segment_textbook(text, book):
    """Textbook: one segment per numbered heading block. Cleaned (not rewritten).
    Pre-first-heading content (title page, ISBN, рецензенты, аннотация) is
    dropped — it's bibliographic noise, not knowledge."""
    segs = []
    cur_path, cur_title, buf = None, None, []

    def flush():
        if cur_path and buf:                     # only emit real, headed sections
            body = "\n".join(buf).strip()
            if len(body) < 40:                   # skip stubs
                return
            crumb = f"{book} > {cur_path} {cur_title}"
            cite = f"{book}, разд. {cur_path}"
            segs.append((crumb, cite, body))

    for ln in text.split("\n"):
        s = ln.strip()
        mh = _match_heading(s)
        if mh:
            flush()
            cur_path, cur_title = mh[0], mh[1]; buf = []
            continue
        if s:
            buf.append(s)
    flush()

    # Fallback: a document whose structure we couldn't detect must NOT be lost.
    # Emit the whole cleaned text as one segment (coarse, but searchable).
    if not segs and text.strip():
        body = text.strip()
        if len(body) > 60:
            segs.append((f"{book} > (полный текст)", book, body))
    return segs


# Reference docs (small, curated, authoritative — e.g. «Срок доставки (факторы)»):
# segment on SINGLE-int numbered groups «1. Заголовок» (sentence-case allowed).
# These are short and high-value, so list-item false positives aren't a concern.
_REF_HEAD = re.compile(r"^(\d{1,2})\.\s+([А-ЯЁ].{3,90})\s*$")


def segment_reference(text, book):
    segs = []
    cur_no, cur_title, buf = None, None, []

    def flush():
        if cur_no and buf:
            body = "\n".join(buf).strip()
            if len(body) < 20:
                return
            crumb = f"{book} > {cur_no}. {cur_title}"
            cite = f"{book}, п. {cur_no} «{cur_title}»"
            segs.append((crumb, cite, (cur_title + "\n" + body).strip()))

    for ln in text.split("\n"):
        s = ln.strip()
        mh = _REF_HEAD.match(s)
        if mh:
            flush()
            cur_no, cur_title, buf = mh.group(1), mh.group(2).strip(), []
            continue
        if s:
            buf.append(s)
    flush()
    if not segs and text.strip():
        segs.append((f"{book} > (полный текст)", book, text.strip()))
    return segs


# Glossary / telegraph-code dictionary (e.g. «Аббревиатуры РЖД»): a flattened
# 3-column table «должность | КОД | адресование», grouped by org-unit headers.
# Segment on the org-unit header lines; keep each unit's role→code block whole.
# A header = a title-case org name with NO embedded telegraph code / «Вся сеть».
_GLOSS_HEAD = re.compile(
    r"^(Аппарат управления|Руководство|Дирекц|Департамент|Управлени|Центр(?:альн)?|"
    r"Служба|Агентств|Отдел|Сектор|Группа|Региональн|[А-ЯЁ][а-яё]+ская железная дорога)"
)
_HAS_CODE = re.compile(r"\b[ЦДНПТФ][А-ЯЁ0-9\-]{1,8}\b")        # telegraph code present


def segment_glossary(text, book):
    """One segment per org-unit block (header + its роли/коды). Reference-style."""
    segs = []
    cur_title, buf = None, []

    def flush():
        if cur_title and buf:
            body = "\n".join(buf).strip()
            if len(body) < 10:
                return
            crumb = f"{book} > {cur_title}"
            cite = f"{book}: {cur_title}"
            segs.append((crumb, cite, (cur_title + "\n" + body).strip()))

    for ln in text.split("\n"):
        s = ln.strip()
        # an org-unit header: matches the header pattern, is short, has no code/«Вся сеть»
        is_header = (_GLOSS_HEAD.match(s) and len(s) < 70
                     and "Вся сеть" not in s and not _HAS_CODE.search(s))
        if is_header:
            flush()
            cur_title, buf = s, []
            continue
        if s:
            buf.append(s)
    flush()
    if not segs and text.strip():
        segs.append((f"{book} > (полный текст)", book, text.strip()))
    return segs


# --------------------------------------------------------------------------
# Emit
# --------------------------------------------------------------------------
def book_name(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"[_]+", " ", stem).strip()
    return stem


def detect_collection(path):
    low = os.path.basename(path).lower()
    if any(k in low for k in ("птэ", "идп", "иси", "приложение", "pte", "idp")):
        return "pte"
    return "textbooks"


def to_markdown(segs, source_file, collection):
    verbatim = collection == "pte"
    out = []
    for crumb, cite, body in segs:
        out.append(f"## {crumb}")
        if not verbatim:
            # 1-line context prefix (faithful — describes, doesn't replace)
            first = body.split("\n", 1)[0][:140]
            out.append(f"> О чём: {first}")
        out.append("")
        out.append(body)
        out.append("")
        out.append(f"_Источник: {cite}_")
        out.append("\n---\n")
    header = (f"<!-- collection={collection} source={os.path.basename(source_file)} "
              f"verbatim={verbatim} segments={len(segs)} -->\n")
    return header + "\n".join(out)


def prepare_file(path, collection, out_dir):
    coll = collection or detect_collection(path)
    ext = os.path.splitext(path)[1].lower()
    raw = extract_docx(path) if ext == ".docx" else extract_pdf(path)
    text = denoise(raw)
    book = book_name(path)
    if coll == "pte":
        segs = segment_regulation(text, book)
    elif coll == "reference":
        segs = segment_reference(text, book)
    elif coll == "glossary":
        segs = segment_glossary(text, book)
    else:
        segs = segment_textbook(text, book)

    dest_dir = os.path.join(out_dir, coll)
    os.makedirs(dest_dir, exist_ok=True)
    stem = re.sub(r"[^\w\-.]+", "_", os.path.splitext(os.path.basename(path))[0])[:80]
    dest = os.path.join(dest_dir, stem + ".md")
    md = to_markdown(segs, path, coll)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  [{coll}] {os.path.basename(path)} -> {dest}  ({len(segs)} segments, {len(text)} chars)")
    return dest, len(segs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="file or directory")
    ap.add_argument("--collection", default="",
                    choices=["", "pte", "textbooks", "reference", "glossary"])
    ap.add_argument("--out", default="kb_out")
    args = ap.parse_args()

    if os.path.isdir(args.src):
        files = []
        for ext in ("*.pdf", "*.docx", "*.DOCX", "*.PDF"):
            files += glob.glob(os.path.join(args.src, "**", ext), recursive=True)
        files = sorted(set(files))
    else:
        files = [args.src]

    print(f"Preparing {len(files)} file(s) -> {args.out}/")
    total_segs = 0
    for fp in files:
        if os.path.basename(fp).startswith("~$"):
            continue
        try:
            _, n = prepare_file(fp, args.collection, args.out)
            total_segs += n
        except Exception as e:
            print(f"  [ERROR] {os.path.basename(fp)}: {e}")
    print(f"DONE. {total_segs} segments total.")


if __name__ == "__main__":
    main()
