# -*- coding: utf-8 -*-
"""Run ONE golden item by id and print full trace.

Usage inside gcu-mcp:
    QID=q3_port python /tmp/golden_one.py
"""
import sys, json, time, urllib.request, os, re
sys.path.insert(0, "/app")
import mcp_postgres_server as S

LM = "http://host.docker.internal:1234/v1/chat/completions"
MODEL = os.environ.get("TEST_MODEL", "qwen3.6-35b-a3b-mtp")
PROMPT = open("/tmp/live_prompt.txt", encoding="utf-8").read()
ITEMS = json.load(open("/tmp/golden8_items.json", encoding="utf-8"))
QID = os.environ.get("QID", "q3_port")
MAX_TURNS = 16

item = next(x for x in ITEMS if x["id"] == QID)

TOOLS = [
 {"type":"function","function":{"name":"gcu-postgres_describe","description":(S.describe.__doc__ or "")[:300],"parameters":{"type":"object","properties":{"table":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_find_indicator","description":(S.find_indicator.__doc__ or "")[:400],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"}},"required":["query"]}}},
 {"type":"function","function":{"name":"gcu-postgres_query","description":(S.query.__doc__ or "")[:200],"parameters":{"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}},
 {"type":"function","function":{"name":"gcu-postgres_search_knowledge","description":(S.search_knowledge.__doc__ or "")[:250],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"},"collection":{"type":"string"}},"required":["query"]}}},
]

def dispatch(name, a):
    if "find_indicator" in name: return S.find_indicator(a.get("query",""), k=a.get("k",5))
    if "describe" in name:        return S.describe(a.get("table",""))
    if "_query" in name:          return S.query(a.get("sql",""))
    if "search_knowledge" in name: return S.search_knowledge(a.get("query",""), k=a.get("k",3), collection=a.get("collection",""))
    return "unknown"

# reset per-question counters
try:
    S._recent_q.clear(); S._consec_zero[0]=0; S._find_calls[0]=0
    S._describe_calls[0]=0; S._query_calls[0]=0; S._tool_calls[0]=0
except Exception: pass

msgs = [{"role":"system","content":PROMPT}, {"role":"user","content":item["q"]}]
print(f"=== {QID} ==="); print("Q:", item["q"]); print("-"*70)

for turn in range(MAX_TURNS):
    body = json.dumps({"model":MODEL, "messages":msgs, "tools":TOOLS, "temperature":0.2, "stream":False}).encode()
    req = urllib.request.Request(LM, data=body, headers={"Content-Type":"application/json"})
    ch = json.load(urllib.request.urlopen(req, timeout=360))["choices"][0]
    m = ch["message"]
    if m.get("tool_calls"):
        msgs.append(m)
        for tc in m["tool_calls"]:
            try: args=json.loads(tc["function"]["arguments"])
            except: args={}
            name=tc["function"]["name"]
            print(f"\n[turn {turn+1}] TOOL {name}")
            print("  args:", json.dumps(args, ensure_ascii=False)[:300])
            res=dispatch(name, args)
            print("  result:", str(res)[:500].replace("\n"," | "))
            msgs.append({"role":"tool","tool_call_id":tc["id"],"content":str(res)[:1900]})
        continue
    ans = m.get("content") or ""
    print("\n" + "="*70); print("ANSWER:\n", ans)
    # numeric coverage
    g = {n.replace(",",".").rstrip("0").rstrip(".") for n in re.findall(r"-?\d+(?:[.,]\d+)?", item["gold"])}
    a = {n.replace(",",".").rstrip("0").rstrip(".") for n in re.findall(r"-?\d+(?:[.,]\d+)?", ans)}
    hit = g & a
    print(f"\ncoverage: {len(hit)}/{len(g)} = {len(hit)/max(1,len(g)):.0%}")
    print(f"missing: {sorted(g - a)}")
    break
else:
    print("TURN-CAP, no answer")
