# -*- coding: utf-8 -*-
"""Test the EXACT verbatim docx questions tied to each error-log item, through the
real MCP tool-loop, and auto-judge the final answer against Postgres ground truth.
Runs INSIDE gcu-mcp. max_tokens high (MoE reasons in <think>).

Each item: (error_id, verbatim_question, [expected_substrings], [forbidden_substrings]).
PASS = all expected present AND no forbidden present in the final answer.
"""
import sys, json, time, urllib.request, re
sys.path.insert(0, "/app")
import mcp_postgres_server as S

LM="http://host.docker.internal:1234/v1/chat/completions"; MODEL="qwen3.6-35b-a3b-mtp"
PROMPT=open("/tmp/live_prompt_current.txt",encoding="utf-8").read()
MAXTOK=4500; TIMEOUT=420; MAX_TURNS=12

TOOLS=[
 {"type":"function","function":{"name":"gcu-postgres_describe","description":(S.describe.__doc__ or"")[:300],"parameters":{"type":"object","properties":{"table":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_find_indicator","description":(S.find_indicator.__doc__ or"")[:400],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"}},"required":["query"]}}},
 {"type":"function","function":{"name":"gcu-postgres_query","description":(S.query.__doc__ or"")[:200],"parameters":{"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}},
 {"type":"function","function":{"name":"gcu-postgres_current_datetime","description":(S.current_datetime.__doc__ or"")[:150],"parameters":{"type":"object","properties":{"timezone":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_search_knowledge","description":(S.search_knowledge.__doc__ or"")[:250],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"},"collection":{"type":"string"}},"required":["query"]}}},
]

# (id, question, expected[], forbidden[])
TESTS=[
 ("E8/Q8 port наличие на сети→порты",
  "Проанализируй наличие вагонов на сети назначением на припортовые станции на 18-00 отчетных суток.",
  ["148 263","148263"], []),
 ("NEW Q port вагоны НА станции",
  "Сколько вагонов фактически находится на самих припортовых станциях по состоянию на 18:00 отчетных суток?",
  ["19 395","19395"], ["148 263","148263"]),
 ("E1/Q21 отказы сетевой итог",
  "Проанализируй отказы технических средств",
  ["234"], []),
 ("E3/Q22 рост отказов by road",
  "Какие подразделения допустили рост отказов технических средств к уровню прошлого года.",
  ["Северо-Кавказская"], ["+1100","1100%"]),
 ("E2/Q23 задержка поездов поездо-часы",
  "Какие дороги и подразделения допустили наибольшую задержку грузовых поездов по причине отказов технических средств.",
  ["101,65","101.65"], ["203,30","203.30"]),
 ("E4/Q14 простой БЕЗ переработки",
  "Проанализируй отклонения от норматива простоя транзитного вагона без переработки. Определи 5 станций с наибольшим превышением норматива (в часах и в процентах). Сделай выводы",
  ["ПЕНЗА"], ["БАТАЙСК","+837","837%"]),
 ("E5/Q13 сорт станции зоны",
  "Проанализируй работу важнейших сортировочных станций.",
  ["ЮДИНО"], []),
 ("Q15 простой С переработкой (control, was correct)",
  "Проанализируй отклонения от норматива простоя транзитного вагона с переработкой. Определи 5 станций с наибольшим превышением норматива (в часах и в процентах). Сделай выводы",
  ["ЮДИНО","195"], []),
 ("E6/Q6 работа припортовых (worst road)",
  "Проанализируй работу припортовых станций.",
  ["54,7","54,8","54.7","54.8"], []),
 ("E9/Q29 ограничения share",
  "На каких дорогах превышается количество и протяженность действующих ограничений скорости движения поездов.",
  ["Горьковская","Свердловская"], []),
]

def call(msgs):
    body=json.dumps({"model":MODEL,"messages":msgs,"tools":TOOLS,"temperature":0.2,"stream":False,"max_tokens":MAXTOK}).encode()
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
for eid,q,exp,forb in TESTS:
    reset()
    msgs=[{"role":"system","content":PROMPT},{"role":"user","content":q}]
    t0=time.time(); sqls=[]; ans=None; err=None
    for turn in range(MAX_TURNS):
        try: ch=call(msgs)
        except Exception as e: err=str(e)[:150]; break
        m=ch["message"]
        if m.get("tool_calls"):
            msgs.append(m)
            for tc in m["tool_calls"]:
                try: a=json.loads(tc["function"]["arguments"])
                except: a={}
                n=tc["function"]["name"]
                if "_query" in n: sqls.append(a.get("sql","")[:200].replace("\n"," "))
                msgs.append({"role":"tool","tool_call_id":tc["id"],"content":str(disp(n,a))[:1900]})
            continue
        ans=m.get("content") or ""; break
    # judge
    na = norm(ans or "")
    exp_ok = all(any(norm(e) in na for e in [ex]) for ex in exp) if exp else True
    forb_hit = [f for f in forb if norm(f) in na]
    verdict = "EMPTY" if not ans else ("PASS" if (exp_ok and not forb_hit) else "FAIL")
    results.append((eid,q,verdict,exp,exp_ok,forb_hit,sqls,ans,round(time.time()-t0,1),err))
    print("\n"+"="*100)
    print(f"[{verdict}] {eid}  ({round(time.time()-t0,1)}s)")
    print("Q:",q[:90])
    print("expected:",exp,"-> present:",exp_ok," | forbidden hit:",forb_hit)
    if sqls: print("last SQL:",sqls[-1][:180])
    print("ANSWER:",(ans or "<EMPTY>")[:700])

print("\n"+"="*100)
p=sum(1 for r in results if r[2]=="PASS"); f=sum(1 for r in results if r[2]=="FAIL"); e=sum(1 for r in results if r[2]=="EMPTY")
print(f"SUMMARY: {p} PASS / {f} FAIL / {e} EMPTY  of {len(results)}")
for r in results: print(f"  {r[2]:6} {r[0]}")
