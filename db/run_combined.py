# -*- coding: utf-8 -*-
"""Run the combined 85-Q suite through the live MCP tool-loop, log everything,
classify 'stuck' behavior, and emit an HTML report (Good/Bad + stuck analysis).

Runs inside gcu-mcp. Needs /tmp/live_prompt.txt and /tmp/questions_combined.py.
Writes /tmp/combined_results.json and /tmp/combined_report.html."""
import sys, json, time, urllib.request, os, html, importlib.util
sys.path.insert(0, "/app")
import mcp_postgres_server as S

LM = "http://host.docker.internal:1234/v1/chat/completions"
MODEL = os.environ.get("TEST_MODEL", "qwen3.6-35b-a3b-mtp")
TIMEOUT = 360
MAX_TURNS = 12
PROMPT = open("/tmp/live_prompt.txt", encoding="utf-8").read()

spec = importlib.util.spec_from_file_location("qc", "/tmp/questions_combined.py")
qc = importlib.util.module_from_spec(spec); spec.loader.exec_module(qc)
LABELED = qc.LABELED

TOOLS = [
 {"type":"function","function":{"name":"gcu-postgres_describe","description":(S.describe.__doc__ or"")[:300],"parameters":{"type":"object","properties":{"table":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_find_indicator","description":(S.find_indicator.__doc__ or"")[:400],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"}},"required":["query"]}}},
 {"type":"function","function":{"name":"gcu-postgres_query","description":(S.query.__doc__ or"")[:200],"parameters":{"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}},
 {"type":"function","function":{"name":"gcu-postgres_current_datetime","description":(S.current_datetime.__doc__ or"")[:150],"parameters":{"type":"object","properties":{"timezone":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_search_knowledge","description":(S.search_knowledge.__doc__ or"")[:250],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"},"collection":{"type":"string"}},"required":["query"]}}},
]

def call_lm(msgs):
    body=json.dumps({"model":MODEL,"messages":msgs,"tools":TOOLS,"temperature":0.2,"stream":False}).encode()
    req=urllib.request.Request(LM,data=body,headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=TIMEOUT))["choices"][0]

def dispatch(name,a):
    if "find_indicator" in name: return S.find_indicator(a.get("query",""),k=a.get("k",5))
    if "describe" in name: return S.describe(a.get("table",""))
    if "_query" in name: return S.query(a.get("sql",""))
    if "current_datetime" in name: return S.current_datetime(a.get("timezone","Europe/Moscow"))
    if "search_knowledge" in name: return S.search_knowledge(a.get("query",""),k=a.get("k",3),collection=a.get("collection",""))
    return "unknown"

def reset():
    try:
        S._recent_q.clear(); S._consec_zero[0]=0; S._find_calls[0]=0
        S._describe_calls[0]=0; S._query_calls[0]=0
    except Exception: pass

def run_one(group, q):
    reset()
    msgs=[{"role":"system","content":PROMPT},{"role":"user","content":q}]
    t0=time.time(); calls=[]; guard_hits=0
    for turn in range(MAX_TURNS):
        try: ch=call_lm(msgs)
        except Exception as e:
            return dict(group=group,q=q,answer=None,calls=calls,sec=round(time.time()-t0,1),
                        err=str(e)[:200],guard_hits=guard_hits,nq=sum(1 for c in calls if c['name'].endswith('_query')))
        m=ch["message"]
        if m.get("tool_calls"):
            msgs.append(m)
            for tc in m["tool_calls"]:
                try: args=json.loads(tc["function"]["arguments"])
                except: args={}
                name=tc["function"]["name"]
                res=dispatch(name,args)
                is_guard=isinstance(res,str) and (res.startswith("⛔") or res.startswith("⚠"))
                if isinstance(res,str) and res.startswith("⛔"): guard_hits+=1
                calls.append({"name":name,"args":args,"guard":is_guard})
                msgs.append({"role":"tool","tool_call_id":tc["id"],"content":str(res)[:1900]})
            continue
        ans=m.get("content") or ""
        nq=sum(1 for c in calls if c['name'].endswith('_query'))
        return dict(group=group,q=q,answer=ans,calls=calls,sec=round(time.time()-t0,1),
                    err=None,guard_hits=guard_hits,nq=nq)
    nq=sum(1 for c in calls if c['name'].endswith('_query'))
    return dict(group=group,q=q,answer=None,calls=calls,sec=round(time.time()-t0,1),
                err="turn-cap",guard_hits=guard_hits,nq=nq)

results=[]
for i,(group,q) in enumerate(LABELED,1):
    r=run_one(group,q)
    results.append(r)
    status="ANS" if r["answer"] else ("CAP" if r["err"]=="turn-cap" else "ERR")
    print("[%2d/%d] %s %-10s calls=%2d nq=%d guard=%d %5.1fs"%(i,len(LABELED),status,group,len(r['calls']),r['nq'],r['guard_hits'],r['sec']),flush=True)
    json.dump(results,open("/tmp/combined_results.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)

# ---------- HTML report ----------
def esc(s): return html.escape(s or "")
tot=len(results); ans=sum(1 for r in results if r["answer"]); cap=sum(1 for r in results if r["err"]=="turn-cap"); err=sum(1 for r in results if r["err"] and r["err"]!="turn-cap")
by_group={}
for g in ("focused","expert","behavioral"):
    rs=[r for r in results if r["group"]==g]
    by_group[g]=(sum(1 for r in rs if r["answer"]),len(rs))
guard_fired=sum(1 for r in results if r["guard_hits"]>0)
avg_nq_ans=round(sum(r["nq"] for r in results if r["answer"])/max(ans,1),1)
avg_nq_cap=round(sum(r["nq"] for r in results if not r["answer"])/max(tot-ans,1),1)

rows_html=[]
for i,r in enumerate(results,1):
    ok = bool(r["answer"])
    cls = "good" if ok else ("err" if r["err"] and r["err"]!="turn-cap" else "bad")
    badge = "OK ОТВЕТ" if ok else ("ЗАСТРЯЛ (cap)" if r["err"]=="turn-cap" else "ОШИБКА")
    tools=" -> ".join(c["name"].split("_")[-1]+("[stop]" if c.get("guard") else "") for c in r["calls"])
    ans_html=esc(r["answer"][:1500]) if r["answer"] else "<i>нет ответа: %s</i>"%esc(r['err'])
    rows_html.append('<div class="card %s"><div class="hd"><span class="badge %s">%s</span> <span class="grp">%s</span> <span class="meta">calls=%d &middot; query=%d &middot; guard=%d &middot; %ss</span></div><div class="q">Q%d. %s</div><div class="tools">%s</div><details><summary>ответ</summary><pre>%s</pre></details></div>'%(cls,cls,badge,r["group"],len(r["calls"]),r["nq"],r["guard_hits"],r["sec"],i,esc(r["q"]),esc(tools),ans_html))

CSS = "body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f4f5f7;color:#1a1a1a}header{background:#c8102e;color:#fff;padding:20px 28px}header h1{margin:0;font-size:22px}header .sub{opacity:.85;font-size:13px;margin-top:4px}.summary{display:flex;gap:14px;flex-wrap:wrap;padding:20px 28px}.stat{background:#fff;border-radius:10px;padding:14px 18px;min-width:120px;box-shadow:0 1px 3px rgba(0,0,0,.08)}.stat .n{font-size:26px;font-weight:700}.stat .l{font-size:12px;color:#666;margin-top:2px}.section-title{padding:8px 28px;font-size:15px;font-weight:700;color:#333}.cards{padding:0 28px 28px;display:grid;gap:12px}.card{background:#fff;border-radius:10px;padding:14px 16px;border-left:5px solid #ccc;box-shadow:0 1px 3px rgba(0,0,0,.06)}.card.good{border-color:#2e7d32}.card.bad{border-color:#ef6c00}.card.err{border-color:#b71c1c}.hd{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.badge{font-size:11px;font-weight:700;padding:3px 8px;border-radius:20px;color:#fff}.badge.good{background:#2e7d32}.badge.bad{background:#ef6c00}.badge.err{background:#b71c1c}.grp{font-size:11px;background:#eee;border-radius:4px;padding:2px 7px;color:#555}.meta{font-size:11px;color:#888;margin-left:auto}.q{font-weight:600;margin:8px 0 6px;font-size:14px}.tools{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#0366d6;background:#f6f8fa;padding:5px 8px;border-radius:6px;word-break:break-all}details{margin-top:8px}summary{cursor:pointer;font-size:12px;color:#555}pre{white-space:pre-wrap;font-size:12px;background:#fafafa;padding:10px;border-radius:6px;max-height:340px;overflow:auto;border:1px solid #eee}.note{background:#fff8e1;border-left:5px solid #f9a825;padding:14px 18px;margin:0 28px 18px;border-radius:8px;font-size:13px}"

doc=("<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\"><title>ЦГЦУ отчёт</title><style>%s</style></head><body>"%CSS
 +"<header><h1>ЦГЦУ AI — отчёт по тесту поведения модели</h1><div class=\"sub\">Модель: %s &middot; вопросов: %d &middot; %s</div></header>"%(esc(MODEL),tot,time.strftime("%Y-%m-%d"))
 +"<div class=\"summary\"><div class=\"stat\"><div class=\"n\" style=\"color:#2e7d32\">%d</div><div class=\"l\">ответили / %d</div></div>"%(ans,tot)
 +"<div class=\"stat\"><div class=\"n\" style=\"color:#ef6c00\">%d</div><div class=\"l\">застряли (turn-cap)</div></div>"%cap
 +"<div class=\"stat\"><div class=\"n\" style=\"color:#b71c1c\">%d</div><div class=\"l\">ошибки</div></div>"%err
 +"<div class=\"stat\"><div class=\"n\">%d</div><div class=\"l\">сработал guard</div></div>"%guard_fired
 +"<div class=\"stat\"><div class=\"n\">%s / %s</div><div class=\"l\">ср.запросов ответ/застрял</div></div></div>"%(avg_nq_ans,avg_nq_cap)
 +"<div class=\"note\"><b>Анализ застревания:</b> отвеченные вопросы используют в среднем <b>%s</b> SQL-запросов, застрявшие <b>%s</b>. Корень: переисследование (много УНИКАЛЬНЫХ запросов, каждый обходит guard идентичных/нулевых). Добавлен guard по ОБЪЁМУ запросов (WARN на %d-м, BLOCK на %d-м).</div>"%(avg_nq_ans,avg_nq_cap,S._QVOL_WARN+1,S._QVOL_BLOCK+1)
 +"<div class=\"section-title\">По группам: focused %d/%d &middot; expert %d/%d &middot; behavioral %d/%d</div>"%(by_group["focused"][0],by_group["focused"][1],by_group["expert"][0],by_group["expert"][1],by_group["behavioral"][0],by_group["behavioral"][1])
 +"<div class=\"cards\">%s</div></body></html>"%("".join(rows_html)))
open("/tmp/combined_report.html","w",encoding="utf-8").write(doc)
print("\n=== DONE: %d/%d answered, %d stuck, %d err. guard fired on %d. ==="%(ans,tot,cap,err,guard_fired))
print("report: /tmp/combined_report.html")
