# -*- coding: utf-8 -*-
import sys, json, urllib.request, time
sys.path.insert(0,"/app"); import mcp_postgres_server as S
LM="http://host.docker.internal:1234/v1/chat/completions"; MODEL="qwen3.6-35b-a3b-mtp"
PROMPT=open("/tmp/live_prompt_current.txt",encoding="utf-8").read()
TOOLS=[
 {"type":"function","function":{"name":"gcu-postgres_describe","description":(S.describe.__doc__ or"")[:300],"parameters":{"type":"object","properties":{"table":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_find_indicator","description":(S.find_indicator.__doc__ or"")[:400],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"}},"required":["query"]}}},
 {"type":"function","function":{"name":"gcu-postgres_query","description":(S.query.__doc__ or"")[:200],"parameters":{"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}},
 {"type":"function","function":{"name":"gcu-postgres_current_datetime","description":(S.current_datetime.__doc__ or"")[:150],"parameters":{"type":"object","properties":{"timezone":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_search_knowledge","description":(S.search_knowledge.__doc__ or"")[:250],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"},"collection":{"type":"string"}},"required":["query"]}}},
]
def call(msgs):
    body=json.dumps({"model":MODEL,"messages":msgs,"tools":TOOLS,"temperature":0.2,"max_tokens":6000}).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(LM,data=body,headers={"Content-Type":"application/json"}),timeout=480))["choices"][0]
def disp(n,a):
    if "find_indicator" in n: return S.find_indicator(a.get("query",""),k=a.get("k",5))
    if "describe" in n: return S.describe(a.get("table",""))
    if "_query" in n: return S.query(a.get("sql",""))
    if "current_datetime" in n: return S.current_datetime(a.get("timezone","Europe/Moscow"))
    if "search_knowledge" in n: return S.search_knowledge(a.get("query",""),k=a.get("k",3),collection=a.get("collection",""))
    return "unknown"
def reset():
    S._recent_q.clear(); S._consec_zero[0]=0; S._find_calls[0]=0; S._describe_calls[0]=0; S._query_calls[0]=0; S._tool_calls[0]=0; S._last_call_ts[0]=0.0
Q=[
 ("Q1 срок доставки","Проанализируй выполнение показателя «Доля грузовых отправок в груженых вагонах, доставленных в срок» по состоянию на 12 марта 2026 года. Представь результаты."),
 ("Q21 отказы","Проанализируй отказы технических средств"),
 ("Q14 простой без переработки","Проанализируй отклонения от норматива простоя транзитного вагона без переработки. Определи 5 станций с наибольшим превышением норматива (в часах и в процентах). Сделай выводы"),
 ("Q23 задержка поездо-часы","Какие дороги и подразделения допустили наибольшую задержку грузовых поездов по причине отказов технических средств."),
 ("Q6 припортовые","Проанализируй работу припортовых станций."),
]
out=[]
for label,q in Q:
    reset()
    msgs=[{"role":"system","content":PROMPT},{"role":"user","content":q}]
    t0=time.time(); sqls=[]
    for t in range(12):
        ch=call(msgs); m=ch["message"]
        if m.get("tool_calls"):
            msgs.append(m)
            for tc in m["tool_calls"]:
                try: a=json.loads(tc["function"]["arguments"])
                except: a={}
                n=tc["function"]["name"]
                if "_query" in n: sqls.append(a.get("sql",""))
                msgs.append({"role":"tool","tool_call_id":tc["id"],"content":str(disp(n,a))[:1900]})
            continue
        ans=m.get("content") or ""; break
    else: ans="<TURN-CAP>"
    out.append({"label":label,"q":q,"ans":ans,"sqls":sqls,"sec":round(time.time()-t0,1)})
    print("done:",label,"(%.0fs, %d queries)"%(time.time()-t0,len(sqls)),flush=True)
json.dump(out,open("/tmp/expert_answers.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("SAVED /tmp/expert_answers.json")
