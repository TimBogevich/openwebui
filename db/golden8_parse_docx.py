# -*- coding: utf-8 -*-
"""Parse the expert docx into 8 (question, gold-answer-block) pairs.

The docx has 4 explicit «Вопрос:» blocks. The third one ('конкретные цифры по
факторам') is a long compendium covering 7 named factor-sections — those headers
are the anchor we split on. This gives 8 self-contained question/golden pairs
without any number hardcoded in this file: everything comes from the docx text.

Output: list of dicts {q, gold} written to /tmp/golden8_items.json (and stdout
if run directly).

Run:
    python db/golden8_parse_docx.py
"""
import json, re, sys, zipfile, os

DOCX = os.environ.get(
    "EXPERT_DOCX",
    r"C:/Users/Iskandar/Desktop/Образец экспертных вопросов.docx",
)


def read_paragraphs(path):
    """Return a list of non-empty paragraph strings from a .docx, preserving order."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    paras_xml = re.findall(r"<w:p[^>]*>(.*?)</w:p>", xml, re.S)
    out = []
    for p in paras_xml:
        # join all <w:t>…</w:t> runs inside the paragraph
        text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).strip()
        if text:
            out.append(text)
    return out


# Section headers used inside Q3's compendium. The compendium covers seven
# named factor blocks (port stations, technical speed, section speed, sort
# stations, failures, restrictions, detained trains, locomotives) — we treat
# each as its own question. The detection is by *prefix* of a paragraph,
# matching how the docx labels each block.
FACTOR_HEADERS = [
    ("port",      "Неэффективное использование перерабатывающей способности"),
    ("tech_speed","Выполнение технической скорости"),
    ("sect_speed","Выполнение средней участковой скорости"),
    ("sort",      "Работа важнейших сортировочных станций"),
    ("failures",  "Отказы в работе технических средств"),
    ("restr",     "Наличие ограничений скорости"),
    ("detained",  "Наличие задержанных"),
    ("loco",      "Локомотивы."),
]


# The eight questions we want to test, paired by ID with how we slice the docx.
# - q1: first «Вопрос:» block + its «Ответ ИИ:»
# - q2: second «Вопрос:» block
# - q3..q9: each factor block under the third «Вопрос:»
# - q-last: the fourth «Вопрос:» (управленческие решения)
QUESTIONS = [
    dict(id="q1_ovrall",  src="vopros1",
         q="Проанализируй выполнение показателя «Доля грузовых отправок в груженых вагонах, доставленных в срок» (показатель 2.1) на 12 марта 2026 за все три периода — сутки, с начала месяца, с начала года."),
    dict(id="q2_causes",  src="vopros2",
         q="Какие основные причины и факторы повлияли на невыполнение этого показателя?"),
    dict(id="q3_port",    src="factor:port",
         q="Приведи цифры по неэффективному использованию перерабатывающей способности припортовых терминалов на 12.03.2026: итог по сети и худшие станции."),
    dict(id="q4_speed",   src="factor:tech_speed+sect_speed",
         q="Какова техническая и участковая скорость по сети на 12.03.2026 и где наибольшее невыполнение?"),
    dict(id="q5_sort",    src="factor:sort",
         q="Проанализируй работу важнейших сортировочных станций на 12.03.2026: где наибольшее превышение простоя транзитного вагона с переработкой."),
    dict(id="q6_fail",    src="factor:failures",
         q="Дай характеристику отказов техсредств 1-2 категории на 12.03.2026: всего по сети, динамика к 2025, по комплексам."),
    dict(id="q7_detained",src="factor:detained",
         q="Сколько отставленных груженых поездов на сети на 12.03.2026, по каким дорогам больше всего и по кодам ответственности РЖД?"),
    dict(id="q8_mgmt",    src="vopros4",
         q="Предложи управленческие решения по вводу показателя доставки в срок в целевое значение."),
]


def slice_vopros(paras):
    """Return a list of (vopros_index, body_paragraphs) for each «Вопрос:» block.
    body_paragraphs starts AFTER the 'Ответ ИИ:' marker (or right after the
    Вопрос paragraph if that marker is absent) and stops at the NEXT Вопрос."""
    starts = [i for i, p in enumerate(paras) if p.startswith("Вопрос:")]
    blocks = []
    for k, idx in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(paras)
        # skip the Вопрос line + an optional 'Ответ ИИ:' line
        body_start = idx + 1
        if body_start < end and paras[body_start].startswith("Ответ ИИ"):
            body_start += 1
        blocks.append(paras[body_start:end])
    return blocks


def slice_factors(vopros3_body):
    """Inside Q3's body, split into named factor-sections by header prefix.
    Returns {factor_id: [paragraphs...]}."""
    # find header positions
    idxs = []
    for i, p in enumerate(vopros3_body):
        for fid, prefix in FACTOR_HEADERS:
            if p.startswith(prefix):
                idxs.append((i, fid))
                break
    out = {}
    for k, (i, fid) in enumerate(idxs):
        end = idxs[k + 1][0] if k + 1 < len(idxs) else len(vopros3_body)
        # body of this factor is the header itself + everything until the next header
        out[fid] = vopros3_body[i:end]
    return out


def build_items():
    paras = read_paragraphs(DOCX)
    vopros = slice_vopros(paras)
    if len(vopros) < 4:
        raise SystemExit(f"docx structure unexpected: found {len(vopros)} «Вопрос:» blocks, want 4")
    factors = slice_factors(vopros[2])

    items = []
    for q in QUESTIONS:
        if q["src"] == "vopros1":
            gold = "\n".join(vopros[0])
        elif q["src"] == "vopros2":
            gold = "\n".join(vopros[1])
        elif q["src"] == "vopros4":
            gold = "\n".join(vopros[3])
        elif q["src"].startswith("factor:"):
            keys = q["src"].split(":", 1)[1].split("+")
            chunks = []
            for k in keys:
                chunks.extend(factors.get(k, []))
            gold = "\n".join(chunks)
        else:
            gold = ""
        items.append(dict(id=q["id"], q=q["q"], gold=gold.strip()))
    return items


def main():
    items = build_items()
    out = "/tmp/golden8_items.json" if os.name != "nt" else "C:/Temp/golden8_items.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    # also print summary
    sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
    print(f"Wrote {len(items)} items to {out}")
    for it in items:
        print(f"\n[{it['id']}]  Q: {it['q'][:70]}")
        print(f"  gold ({len(it['gold'])} chars): {it['gold'][:120]}")


if __name__ == "__main__":
    main()
