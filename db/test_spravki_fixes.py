# -*- coding: utf-8 -*-
"""Live end-to-end test of the 3 spravki fixes through the real MCP tool-loop.
Runs INSIDE gcu-mcp. Drives LM Studio (:1234) with the live tools, dispatches to
the real MCP server, and prints every tool call + final answer so we can verify
the model picks the CORRECT columns (not just that the data is right).

Usage: docker exec gcu-mcp python /tmp/test_spravki_fixes.py
"""
import sys, json, time, urllib.request
sys.path.insert(0, "/app")
import mcp_postgres_server as S

LM = "http://host.docker.internal:1234/v1/chat/completions"
MODEL = "qwen3.6-35b-a3b-mtp"
TIMEOUT = 360
MAX_TURNS = 12
MAXTOK = 2000  # reasoning model needs headroom (HANDOFF)
PROMPT = open("/tmp/live_prompt_current.txt", encoding="utf-8").read()

# The 3 questions that each fix is supposed to make answerable correctly,
# plus the expected ground-truth value (verified earlier against Postgres).
TESTS = [
 ("PORT: вагоны НА станции (fix #3)",
  "Проанализируй наличие вагонов на сети назначением на припортовые станции на 18-00 отчетных суток.",
  "Назначением на сеть→порты = 148263 (НЕ 19395)."),
 ("PORT: вагоны на самих станциях (fix #3)",
  "Сколько вагонов фактически находится НА самих припортовых станциях на 18:00?",
  "На станции 18:00 = 19395 (НЕ 148263)."),
 ("FAILURES: задержка по дорогам (fix #1, no double-count)",
  "Какие дороги допустили наибольшую задержку грузовых поездов по причине отказов технических средств? Дай топ-5 по поездо-часам.",
  "Свердловская 101.65 / ВСиб 93.15 / ОКТ 74.78 / ДВ 69.03 / Приволж 46.92 (НЕ удвоенные 203.30/183.47…)."),
 ("SORT: простой БЕЗ переработки (fix #2)",
  "Проанализируй отклонения от норматива простоя транзитного вагона БЕЗ переработки. Определи 5 станций с наибольшим превышением норматива. Сделай выводы.",
  "ПЕНЗА III +3.3ч, АЛТАЙСКАЯ +2.67, СЫЗРАНЬ I +2.08 (НЕ БАТАЙСК +20.78/ЮДИНО)."),
]

TOOLS = [
 {"type":"function","function":{"name":"gcu-postgres_describe","description":(S.describe.__doc__ or"")[:300],"parameters":{"type":"object","properties":{"table":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_find_indicator","description":(S.find_indicator.__doc__ or"")[:400],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"}},"required":["query"]}}},
 {"type":"function","function":{"name":"gcu-postgres_query","description":(S.query.__doc__ or"")[:200],"parameters":{"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}},
 {"type":"function","function":{"name":"gcu-postgres_current_datetime","description":(S.current_datetime.__doc__ or"")[:150],"parameters":{"type":"object","properties":{"timezone":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_search_knowledge","description":(S.search_knowledge.__doc__ or"")[:250],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"},"collection":{"type":"string"}},"required":["query"]}}},
]

def call_lm(msgs):
    body=json.dumps({"model":MODEL,"messages":msgs,"tools":TOOLS,"temperature":0.2,"stream":False,"max_tokens":MAXTOK}).encode()
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
        S._describe_calls[0]=0; S._query_calls[0]=0; S._tool_calls[0]=0
    except Exception: pass

def run_one(label, q, expect):
    reset()
    print("\n"+"="*100)
    print("TEST:", label)
    print("Q:", q)
    print("EXPECT:", expect)
    print("-"*100)
    msgs=[{"role":"system","content":PROMPT},{"role":"user","content":q}]
    t0=time.time()
    for turn in range(MAX_TURNS):
        try: ch=call_lm(msgs)
        except Exception as e:
            print("  LM ERROR:", str(e)[:200]); return
        m=ch["message"]
        if m.get("tool_calls"):
            msgs.append(m)
            for tc in m["tool_calls"]:
                try: args=json.loads(tc["function"]["arguments"])
                except: args={}
                name=tc["function"]["name"]
                # SHOW the SQL the model wrote — this reveals which columns it uses
                if "_query" in name:
                    print("  SQL:", (args.get("sql","")[:280]).replace("\n"," "))
                elif "describe" in name:
                    print("  describe(", args.get("table",""),")")
                elif "find_indicator" in name:
                    print("  find_indicator(", args.get("query","")[:60],")")
                res=dispatch(name,args)
                msgs.append({"role":"tool","tool_call_id":tc["id"],"content":str(res)[:1900]})
            continue
        ans=m.get("content") or ""
        print("-"*100)
        print("ANSWER (%.1fs):"%(time.time()-t0))
        print(ans[:1600])
        return
    print("  [TURN-CAP — no answer in %d turns]"%MAX_TURNS)

if __name__=="__main__":
    for label,q,expect in TESTS:
        run_one(label,q,expect)
    print("\n"+"="*100+"\nDONE")
