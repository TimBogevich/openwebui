# -*- coding: utf-8 -*-
"""Run the 8 golden questions (parsed live from the expert docx) through the
live model + MCP tool-loop, score each answer against the docx-derived gold,
and emit an HTML report.

No numbers are hardcoded in this file or the harness — the gold answers come
from db/golden8_parse_docx.py which reads the docx at run time. Replace the
docx and the harness picks up the new gold automatically.

Runs inside gcu-mcp:
    docker cp db/golden8_parse_docx.py gcu-mcp:/tmp/
    docker cp /Temp/golden8_items.json gcu-mcp:/tmp/
    docker cp db/live_prompt.txt gcu-mcp:/tmp/
    docker cp db/golden8_run.py  gcu-mcp:/tmp/
    docker exec gcu-mcp python //tmp/golden8_run.py
"""
import sys, json, time, urllib.request, os, html, re

sys.path.insert(0, "/app")
import mcp_postgres_server as S

LM = "http://host.docker.internal:1234/v1/chat/completions"
MODEL = os.environ.get("TEST_MODEL", "qwen3.6-35b-a3b-mtp")
PROMPT = open("/tmp/live_prompt.txt", encoding="utf-8").read()
ITEMS = json.load(open("/tmp/golden8_items.json", encoding="utf-8"))
MAX_TURNS = 16

TOOLS = [
 {"type":"function","function":{"name":"gcu-postgres_describe","description":(S.describe.__doc__ or "")[:300],"parameters":{"type":"object","properties":{"table":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_find_indicator","description":(S.find_indicator.__doc__ or "")[:400],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"}},"required":["query"]}}},
 {"type":"function","function":{"name":"gcu-postgres_query","description":(S.query.__doc__ or "")[:200],"parameters":{"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}},
 {"type":"function","function":{"name":"gcu-postgres_search_knowledge","description":(S.search_knowledge.__doc__ or "")[:250],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"},"collection":{"type":"string"}},"required":["query"]}}},
]


def call(msgs):
    body = json.dumps({"model": MODEL, "messages": msgs, "tools": TOOLS,
                       "temperature": 0.2, "stream": False}).encode()
    req = urllib.request.Request(LM, data=body, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=360))["choices"][0]


def dispatch(name, a):
    if "find_indicator" in name: return S.find_indicator(a.get("query", ""), k=a.get("k", 5))
    if "describe" in name:        return S.describe(a.get("table", ""))
    if "_query" in name:          return S.query(a.get("sql", ""))
    if "search_knowledge" in name:
        return S.search_knowledge(a.get("query", ""), k=a.get("k", 3),
                                   collection=a.get("collection", ""))
    return "unknown"


# -- Fact-extraction scoring -----------------------------------------------
# Pull all "numeric facts" (number + nearby unit/word) out of the gold text
# and check how many of those facts appear verbatim (number-wise) in the
# model's answer. This is intentionally tolerant: small punctuation/decimal-
# separator differences are normalised; the comparison is on the numbers
# themselves, not the surrounding prose. So it survives style drift but
# fails when the model invents or omits a key figure.
_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def normalize_num(s):
    """'96,5' -> '96.5'; '1 399' -> '1399'."""
    s = s.replace(" ", "").replace(" ", "").replace(",", ".")
    # strip trailing zeros after decimal so 96.50 == 96.5
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def numbers_in(text):
    """Return a set of normalised numeric strings found in the text."""
    return {normalize_num(m) for m in _NUM_RE.findall(text or "")}


def score(answer, gold):
    """Coverage = fraction of gold numbers that appear in the answer."""
    g = numbers_in(gold)
    a = numbers_in(answer)
    if not g:
        return 1.0, 0, 0, set()
    hit = g & a
    return len(hit) / len(g), len(hit), len(g), g - a   # ratio, hits, total, missing


# -- Run --------------------------------------------------------------------
msgs = [{"role": "system", "content": PROMPT}]
results = []
for qi, it in enumerate(ITEMS, 1):
    if qi > 1:
        time.sleep(S._NEWQ_GAP_S + 3)   # trigger server's per-question TTL reset
    msgs.append({"role": "user", "content": it["q"]})
    calls = []
    t0 = time.time()
    answer = None
    for turn in range(MAX_TURNS):
        ch = call(msgs)
        m = ch["message"]
        if m.get("tool_calls"):
            msgs.append(m)
            for tc in m["tool_calls"]:
                try:    args = json.loads(tc["function"]["arguments"])
                except: args = {}
                name = tc["function"]["name"]
                res = dispatch(name, args)
                calls.append(name.split("_")[-1])
                msgs.append({"role": "tool", "tool_call_id": tc["id"],
                              "content": str(res)[:1900]})
            continue
        answer = m.get("content") or ""
        msgs.append({"role": "assistant", "content": answer})
        break

    cov, hits, total, missing = score(answer, it["gold"])
    results.append(dict(id=it["id"], q=it["q"], gold=it["gold"], answer=answer,
                         calls=calls, sec=round(time.time() - t0, 1),
                         coverage=cov, hits=hits, total=total,
                         missing=sorted(missing)))
    print(f"[{qi}/{len(ITEMS)}] {it['id']:12s}  calls={len(calls):2d}  "
          f"cov={cov:5.1%} ({hits}/{total})  {round(time.time()-t0,1)}s",
          flush=True)
    json.dump(results, open("/tmp/golden8_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


# -- HTML report ------------------------------------------------------------
def esc(s): return html.escape(s or "")
n_ans = sum(1 for r in results if r["answer"])
avg_cov = sum(r["coverage"] for r in results) / max(1, len(results))

cards = []
for i, r in enumerate(results, 1):
    ans = r["answer"] or ""
    cited = "источник" in ans.lower()
    redz  = "красн"   in ans.lower()
    emoji = re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", ans)
    tbls  = [t for t in ("spravki_", "load_fact", "row_level", "day_fact",
                          "delay_code", "month_fact", "road_codes",
                          "delay_reason_codes") if t in ans]
    chips = [
        f'<span class="chip {"ok" if r["coverage"] >= 0.7 else "warn" if r["coverage"] >= 0.4 else "bad"}">'
        f'cov {r["coverage"]:.0%} ({r["hits"]}/{r["total"]})</span>',
        f'<span class="chip {"ok" if cited else "warn"}">источник: {"да" if cited else "—"}</span>',
        f'<span class="chip {"ok" if redz else "warn"}">зона словом: {"да" if redz else "—"}</span>',
        f'<span class="chip {"bad" if emoji else "ok"}">эмодзи: {"".join(emoji[:5]) if emoji else "нет"}</span>',
        f'<span class="chip {"bad" if tbls else "ok"}">имена таблиц: {", ".join(tbls) if tbls else "нет"}</span>',
    ]
    miss = (", ".join(r["missing"][:10]) +
            (f" …+{len(r['missing'])-10}" if len(r["missing"]) > 10 else "")) if r["missing"] else "—"
    tools = " → ".join(r["calls"])
    cards.append(
        f'<div class="card"><div class="qh">Вопрос {i} · {esc(r["id"])}</div>'
        f'<div class="q">{esc(r["q"])}</div>'
        f'<div class="meta">{len(r["calls"])} вызовов · {r["sec"]}s · {"".join(chips)}</div>'
        f'<div class="cols"><div class="col"><div class="lbl gold">ЭТАЛОН (из docx)</div>'
        f'<pre>{esc(r["gold"])}</pre></div>'
        f'<div class="col"><div class="lbl ai">ОТВЕТ МОДЕЛИ</div>'
        f'<pre>{esc(r["answer"]) if r["answer"] else "<i>нет ответа</i>"}</pre></div></div>'
        f'<div class="tools">инструменты: {esc(tools)}</div>'
        f'<div class="miss">пропущенные числа эталона: <code>{esc(miss)}</code></div>'
        f"</div>"
    )

CSS = ("body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f4f5f7;color:#1a1a1a}"
       "header{background:#c8102e;color:#fff;padding:18px 26px}header h1{margin:0;font-size:21px}"
       ".sub{opacity:.9;font-size:13px;margin-top:3px}.wrap{padding:18px 26px;display:grid;gap:16px}"
       ".card{background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 1px 4px rgba(0,0,0,.08)}"
       ".qh{font-size:12px;color:#c8102e;font-weight:700}.q{font-weight:600;margin:3px 0 8px;font-size:15px}"
       ".meta{font-size:12px;color:#777;margin-bottom:10px}"
       ".chip{font-size:11px;padding:2px 8px;border-radius:20px;margin-left:6px;display:inline-block}"
       ".chip.ok{background:#e8f5e9;color:#2e7d32;border:1px solid #a5d6a7}"
       ".chip.warn{background:#fff3e0;color:#e65100;border:1px solid #ffcc80}"
       ".chip.bad{background:#ffebee;color:#b71c1c;border:1px solid #ef9a9a}"
       ".cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}"
       "@media(max-width:900px){.cols{grid-template-columns:1fr}}"
       ".col{background:#fafafa;border-radius:8px;padding:10px;border:1px solid #eee}"
       ".lbl{font-size:11px;font-weight:700;margin-bottom:6px;padding:2px 6px;border-radius:4px;display:inline-block}"
       ".lbl.gold{background:#fff3e0;color:#e65100}.lbl.ai{background:#e3f2fd;color:#1565c0}"
       "pre{white-space:pre-wrap;font-size:12.5px;margin:0;line-height:1.45;max-height:420px;overflow:auto}"
       ".tools{font-family:ui-monospace,monospace;font-size:11px;color:#0366d6;margin-top:8px}"
       ".miss{font-size:11px;color:#b71c1c;margin-top:6px}.miss code{background:#fff5f5}")

doc = ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
       '<title>Сравнение: 8 эталонных вопросов</title>'
       f'<style>{CSS}</style></head><body><header>'
       '<h1>ЦГЦУ — сравнение ответов модели с эталоном (8 вопросов)</h1>'
       f'<div class="sub">{esc(MODEL)} · ответили {n_ans}/{len(results)} · '
       f'средняя покрытие чисел: {avg_cov:.0%} · '
       f'{time.strftime("%Y-%m-%d %H:%M")}</div>'
       f'</header><div class="wrap">{"".join(cards)}</div></body></html>')

open("/tmp/golden8_report.html", "w", encoding="utf-8").write(doc)
print(f"\n=== {n_ans}/{len(results)} answered · avg coverage {avg_cov:.0%} · "
      f"report: /tmp/golden8_report.html ===")
