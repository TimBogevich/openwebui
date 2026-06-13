# -*- coding: utf-8 -*-
"""8 expert questions as ONE session, mirroring real Open WebUI:
NO manual counter resets — relies solely on the MCP server's own per-question
TTL reset (idle gap > _NEWQ_GAP_S between questions). A short real sleep between
questions triggers that reset, proving the agent does not brick across a session."""
import sys, json, time, urllib.request, os
sys.path.insert(0, "/app")
import mcp_postgres_server as S

LM = "http://host.docker.internal:1234/v1/chat/completions"
MODEL = os.environ.get("TEST_MODEL", "qwen3.6-35b-a3b-mtp")
PROMPT = open("/tmp/live_prompt.txt", encoding="utf-8").read()

QUESTIONS = [
 "Проанализируй выполнение показателя «Доля грузовых отправок в груженых вагонах, доставленных в срок» (показатель 2.1) на 12 марта 2026 года за все три периода — сутки, с начала месяца, с начала года.",
 "Какие основные причины и факторы повлияли на невыполнение этого показателя? Приведи структуру задержанных поездов по кодам причин (итог по сети).",
 "Приведи цифры по неэффективному использованию перерабатывающей способности припортовых терминалов на 12.03.2026: итог по сети и худшие станции.",
 "Какова техническая и участковая скорость по сети на 12.03.2026 и где наибольшее невыполнение?",
 "Проанализируй работу важнейших сортировочных станций на 12.03.2026: где наибольшее превышение простоя транзитного вагона с переработкой.",
 "Дай характеристику отказов техсредств 1-2 категории на 12.03.2026: всего по сети, динамика к 2025, по комплексам.",
 "Сколько отставленных груженых поездов на сети на 12.03.2026, по каким дорогам больше всего и по кодам ответственности РЖД?",
 "Предложи управленческие решения по вводу показателя доставки в срок в целевое значение.",
]

TOOLS = [
 {"type":"function","function":{"name":"gcu-postgres_describe","description":(S.describe.__doc__ or"")[:300],"parameters":{"type":"object","properties":{"table":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_find_indicator","description":(S.find_indicator.__doc__ or"")[:400],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"}},"required":["query"]}}},
 {"type":"function","function":{"name":"gcu-postgres_query","description":(S.query.__doc__ or"")[:200],"parameters":{"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}},
]

def call(msgs):
    body=json.dumps({"model":MODEL,"messages":msgs,"tools":TOOLS,"temperature":0.2,"stream":False}).encode()
    req=urllib.request.Request(LM,data=body,headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=300))["choices"][0]

def dispatch(name,a):
    if "find_indicator" in name: return S.find_indicator(a.get("query",""),k=a.get("k",5))
    if "describe" in name: return S.describe(a.get("table",""))
    if "_query" in name: return S.query(a.get("sql",""))
    return "unknown"

msgs=[{"role":"system","content":PROMPT}]
results=[]
for qi,q in enumerate(QUESTIONS,1):
    # NO manual reset. Sleep > _NEWQ_GAP_S so the server's own TTL reset fires,
    # exactly like a user pausing to read the previous answer before asking next.
    if qi>1:
        time.sleep(S._NEWQ_GAP_S + 3)
    msgs.append({"role":"user","content":q})
    calls=[]; first_bricked=False
    for turn in range(14):
        ch=call(msgs); m=ch["message"]
        if m.get("tool_calls"):
            msgs.append(m)
            for tc in m["tool_calls"]:
                try: args=json.loads(tc["function"]["arguments"])
                except: args={}
                name=tc["function"]["name"]
                res=dispatch(name,args)
                if len(calls)==0 and isinstance(res,str) and res.startswith("⛔"):
                    first_bricked=True
                calls.append(name.split("_")[-1])
                msgs.append({"role":"tool","tool_call_id":tc["id"],"content":str(res)[:1900]})
            continue
        ans=m.get("content") or ""
        msgs.append({"role":"assistant","content":ans})
        results.append({"q":q,"answer":ans,"calls":calls,"first_bricked":first_bricked})
        print("Q%d: %s | %d calls | first_call_bricked=%s" % (qi, "ANS" if ans else "EMPTY", len(calls), first_bricked), flush=True)
        break
    else:
        results.append({"q":q,"answer":None,"calls":calls,"first_bricked":first_bricked})
        print("Q%d: CAP | %d calls | first_call_bricked=%s" % (qi, len(calls), first_bricked), flush=True)

json.dump(results, open("/tmp/chain8_realistic.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
ans=sum(1 for r in results if r["answer"]); bricked=sum(1 for r in results if r["first_bricked"])
print("\n=== %d/8 answered, %d first-call-bricked (want 0) ===" % (ans, bricked))
