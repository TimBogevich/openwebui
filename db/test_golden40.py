# -*- coding: utf-8 -*-
"""Golden-40: the ORIGINAL 40Q benchmark (db/questions_40.py — metrics, Apr2026/Mar2022)
through the live MCP tool-loop, WITH the OWI post-processor applied to each final answer
(exactly as the OWI outlet filter would). Captures raw + post-processed answer + SQL.
Runs INSIDE gcu-mcp. Writes /tmp/golden40_answers.json."""
import sys, json, urllib.request, time, importlib.util
sys.path.insert(0,"/app"); import mcp_postgres_server as S

# load the OWI post-processor and apply it to each answer (mirror the outlet filter)
_spec = importlib.util.spec_from_file_location("pp", "/tmp/owi_answer_postprocessor.py")
_pp = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_pp)
POST = _pp.Filter()

LM="http://host.docker.internal:1234/v1/chat/completions"; MODEL="qwen3.6-35b-a3b-mtp"
PROMPT=open("/tmp/live_prompt.txt",encoding="utf-8").read()
QS=json.load(open("/tmp/_questions40.json",encoding="utf-8"))
MAXTOK=6000; TIMEOUT=480; MAX_TURNS=12

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
    S._recent_q.clear(); S._consec_zero[0]=0; S._find_calls[0]=0; S._describe_calls[0]=0; S._query_calls[0]=0; S._tool_calls[0]=0; S._last_call_ts[0]=0.0

out=[]
for i,q in enumerate(QS,1):
    reset()
    msgs=[{"role":"system","content":PROMPT},{"role":"user","content":q}]
    t0=time.time(); sqls=[]; raw=None
    for t in range(MAX_TURNS):
        try: ch=call(msgs)
        except Exception as e: raw="<ERROR:%s>"%str(e)[:100]; break
        m=ch["message"]
        if m.get("tool_calls"):
            msgs.append(m)
            for tc in m["tool_calls"]:
                try: a=json.loads(tc["function"]["arguments"])
                except: a={}
                n=tc["function"]["name"]
                if "_query" in n: sqls.append(a.get("sql",""))
                msgs.append({"role":"tool","tool_call_id":tc["id"],"content":str(disp(n,a))[:1900]})
            continue
        raw=m.get("content") or ""; break
    else: raw="<TURN-CAP>"
    # apply the post-processor (what the user actually sees)
    final = POST._process(raw) if raw and not raw.startswith("<") else raw
    out.append({"n":i,"q":q,"raw":raw,"answer":final,"sqls":sqls,"sec":round(time.time()-t0,1),
                "pp_changed": (final!=raw)})
    status="EMPTY" if not raw else ("CAP" if raw=="<TURN-CAP>" else "ANS")
    print("[%2d/40] %-5s %dq %5.1fs %s  %s"%(i,status,len(sqls),round(time.time()-t0,1),
          "[pp]" if final!=raw else "    ", q[:48]),flush=True)
    json.dump(out,open("/tmp/golden40_answers.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("SAVED /tmp/golden40_answers.json")
