# -*- coding: utf-8 -*-
"""Full regression: all 32 verbatim docx questions through the live MCP tool-loop.
Runs INSIDE gcu-mcp. max_tokens=6000 (MoE reasons in <think> — lower truncates).
Auto-judges the subset with known ground truth; logs SQL+answer for ALL.
Writes /tmp/all32_results.json + prints a summary."""
import sys, json, time, urllib.request
sys.path.insert(0,"/app"); import mcp_postgres_server as S

LM="http://host.docker.internal:1234/v1/chat/completions"; MODEL="qwen3.6-35b-a3b-mtp"
PROMPT=open("/tmp/live_prompt_current.txt",encoding="utf-8").read()
QS=json.load(open("/tmp/_questions32.json",encoding="utf-8"))
MAXTOK=6000; TIMEOUT=480; MAX_TURNS=12

# Ground-truth assertions keyed by question index (1-based, matches docx order).
# expect = must appear; forbid = must NOT appear. Only set where verified vs Postgres.
GT={
 1:(["96,53","96.53"],[]),                       # срок доставки
 3:(["38,0","38.0"],[]),                          # участковая сеть
 8:(["148 263","148263"],[]),                     # наличие на сети→порты
 10:(["73 241","73241"],[]),                      # наличие на дорогах→порты (ДВ)
 11:(["17 119","17119"],["54,0"]),                # выгрузка vs мощность
 14:(["ПЕНЗА"],["БАТАЙСК","+837","837%"]),        # простой без переработки (fix)
 15:(["ЮДИНО","195"],[]),                         # простой с переработкой (control)
 16:(["АГРЫЗ","1228"],[]),                         # рабочий парк top
 17:(["43,3","43.3"],[]),                         # техническая сеть
 19:(["475"],[]),                                 # отставленные всего
 20:(["86"],[]),                                  # по ответственности РЖД (прямые=86)
 21:(["234"],[]),                                 # отказы итог (fix: scope)
 22:(["Северо-Кавказская"],["+1100","1100%"]),    # рост отказов (fix: no double)
 23:(["101,65","101.65"],["203,30","203.30"]),    # задержка поездо-часы (fix)
 26:(["171"],[]),                                 # локомотивы недосодержание С-Зап
 28:(["1893"],[]),                                # ограничения всего
 29:(["327","Горьковская"],[]),                   # ограничения by road
}

TOOLS=[
 {"type":"function","function":{"name":"gcu-postgres_describe","description":(S.describe.__doc__ or"")[:300],"parameters":{"type":"object","properties":{"table":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_find_indicator","description":(S.find_indicator.__doc__ or"")[:400],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"}},"required":["query"]}}},
 {"type":"function","function":{"name":"gcu-postgres_query","description":(S.query.__doc__ or"")[:200],"parameters":{"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}},
 {"type":"function","function":{"name":"gcu-postgres_current_datetime","description":(S.current_datetime.__doc__ or"")[:150],"parameters":{"type":"object","properties":{"timezone":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_search_knowledge","description":(S.search_knowledge.__doc__ or"")[:250],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"},"collection":{"type":"string"}},"required":["query"]}}},
]
def call(msgs):
    body=json.dumps({"model":MODEL,"messages":msgs,"tools":TOOLS,"temperature":0.2,"max_tokens":MAXTOK}).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(LM,data=body,headers={"Content-Type":"application/json"}),timeout=TIMEOUT))["choices"][0]
def disp(n,a):
    if "find_indicator" in n: return S.find_indicator(a.get("query",""),k=a.get("k",5))
    if "describe" in n: return S.describe(a.get("table",""))
    if "_query" in n: return S.query(a.get("sql",""))
    if "current_datetime" in n: return S.current_datetime(a.get("timezone","Europe/Moscow"))
    if "search_knowledge" in n: return S.search_knowledge(a.get("query",""),k=a.get("k",3),collection=a.get("collection",""))
    return "unknown"
def reset():
    try:
        S._recent_q.clear(); S._consec_zero[0]=0; S._find_calls[0]=0; S._describe_calls[0]=0; S._query_calls[0]=0; S._tool_calls[0]=0
    except: pass
def norm(s): return s.replace(" "," ").replace(" ","").lower()

results=[]
for i,q in enumerate(QS,1):
    reset()
    msgs=[{"role":"system","content":PROMPT},{"role":"user","content":q}]
    t0=time.time(); sqls=[]; ans=None; err=None
    for turn in range(MAX_TURNS):
        try: ch=call(msgs)
        except Exception as e: err=str(e)[:120]; break
        m=ch["message"]
        if m.get("tool_calls"):
            msgs.append(m)
            for tc in m["tool_calls"]:
                try: a=json.loads(tc["function"]["arguments"])
                except: a={}
                n=tc["function"]["name"]
                if "_query" in n: sqls.append(a.get("sql","")[:160].replace("\n"," "))
                msgs.append({"role":"tool","tool_call_id":tc["id"],"content":str(disp(n,a))[:1900]})
            continue
        ans=m.get("content") or ""; break
    sec=round(time.time()-t0,1)
    na=norm(ans or "")
    if i in GT:
        exp,forb=GT[i]
        exp_ok=all(norm(e) in na for e in exp)
        fhit=[f for f in forb if norm(f) in na]
        v="EMPTY" if not ans else ("PASS" if (exp_ok and not fhit) else "FAIL")
    else:
        v="EMPTY" if not ans else ("ANS" if not err else "ERR")
    results.append(dict(i=i,q=q,verdict=v,sec=sec,nq=len(sqls),sqls=sqls,ans=ans,err=err))
    tag=("GT:" if i in GT else "")
    print("[%2d] %-5s %sturns_sql=%d %5.1fs  %s"%(i,v,tag,len(sqls),sec,q[:62]),flush=True)
    json.dump(results,open("/tmp/all32_results.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)

gt=[r for r in results if r["i"] in GT]
print("\n"+"="*80)
print("GROUND-TRUTH SUBSET: %d PASS / %d FAIL / %d EMPTY of %d"%(
  sum(1 for r in gt if r["verdict"]=="PASS"),sum(1 for r in gt if r["verdict"]=="FAIL"),
  sum(1 for r in gt if r["verdict"]=="EMPTY"),len(gt)))
print("ALL 32: %d answered / %d empty / %d err"%(
  sum(1 for r in results if r["ans"]),sum(1 for r in results if not r["ans"] and not r["err"]),
  sum(1 for r in results if r["err"])))
print("\nGT failures/empties to inspect:")
for r in gt:
    if r["verdict"]!="PASS": print("  [%d] %s — %s"%(r["i"],r["verdict"],r["q"][:60]))
