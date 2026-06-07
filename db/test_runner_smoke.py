# -*- coding: utf-8 -*-
"""Small smoke test: 4 spravki-routing questions."""
import json, time, urllib.request, sys
sys.path.insert(0, "/app")
import mcp_postgres_server as S

LM = "http://host.docker.internal:1234/v1/chat/completions"
MODEL = "qwen3.6-35b-a3b"
MAX_TURNS = 10

QUESTIONS = [
    "Сколько задержанных поездов по коду 22 на 12.03.2026 по дорогам?",
    "Какова техническая скорость на Дальневосточной дороге за 12.03.2026?",
    "Сколько отказов техсредств зафиксировано на Октябрьской дороге за 12.03.2026?",
    "Какой парк локомотивов на Восточном полигоне на 12.03.2026?",
]

def get_prompt():
    return open("/tmp/live_prompt.txt", encoding="utf-8").read()

TOOLS = [
    {"type":"function","function":{
        "name":"gcu-postgres_describe",
        "description":(S.describe.__doc__ or "")[:300],
        "parameters":{"type":"object","properties":{"table":{"type":"string"}}}}},
    {"type":"function","function":{
        "name":"gcu-postgres_query",
        "description":(S.query.__doc__ or "")[:200],
        "parameters":{"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}},
    {"type":"function","function":{
        "name":"gcu-postgres_current_datetime",
        "description":(S.current_datetime.__doc__ or "")[:200],
        "parameters":{"type":"object","properties":{"timezone":{"type":"string"}}}}},
    {"type":"function","function":{
        "name":"gcu-postgres_search_knowledge",
        "description":(S.search_knowledge.__doc__ or "")[:300],
        "parameters":{"type":"object","properties":{
            "query":{"type":"string"},"k":{"type":"integer"},"collection":{"type":"string"}},
            "required":["query"]}}},
]

def call_lm(messages):
    body = json.dumps({"model":MODEL,"messages":messages,"tools":TOOLS,
                       "temperature":0.2,"stream":False}).encode()
    req = urllib.request.Request(LM, data=body, headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req, timeout=360))["choices"][0]

def dispatch(name, args):
    if "describe" in name: return S.describe(args.get("table",""))
    if "_query" in name: return S.query(args.get("sql",""))
    if "current_datetime" in name: return S.current_datetime(args.get("timezone","Europe/Moscow"))
    if "search_knowledge" in name:
        return S.search_knowledge(args.get("query",""), k=args.get("k",3), collection=args.get("collection",""))
    return f"unknown: {name}"

def run_one(num, q):
    print(f"\n{'='*72}\nQ{num}: {q}\n{'='*72}", flush=True)
    S._recent_q.clear()
    msgs = [{"role":"system","content":get_prompt()},
            {"role":"user","content":q}]
    t0 = time.time()
    tool_calls = []
    for turn in range(MAX_TURNS):
        try: ch = call_lm(msgs)
        except Exception as e:
            return {"q":q,"calls":tool_calls,"answer":None,"sec":round(time.time()-t0,1),"err":str(e)[:200]}
        m = ch["message"]
        if m.get("tool_calls"):
            msgs.append(m)
            for tc in m["tool_calls"]:
                name = tc["function"]["name"]
                try: args = json.loads(tc["function"]["arguments"])
                except: args = {}
                primary = list(args.values())[0] if args else ""
                snippet = str(primary)[:90].replace("\n"," ")
                print(f"  [t{turn+1}] -> {name}({snippet})", flush=True)
                tool_calls.append({"name":name,"args":args})
                result = dispatch(name, args)
                if not isinstance(result, str): result = str(result)
                msgs.append({"role":"tool","tool_call_id":tc["id"],"content":result[:1800]})
            continue
        content = m.get("content") or ""
        sec = round(time.time()-t0, 1)
        print(f"  [{len(tool_calls)} calls, {sec}s]", flush=True)
        print(f"  ANSWER: {content[:200]}", flush=True)
        return {"q":q,"calls":tool_calls,"answer":content,"sec":sec,"err":None}
    sec = round(time.time()-t0, 1)
    print(f"  [CAP HIT {sec}s]", flush=True)
    return {"q":q,"calls":tool_calls,"answer":None,"sec":sec,"err":"turn-cap"}

if __name__ == "__main__":
    print(f"MODEL = {MODEL}")
    print(f"prompt len = {len(get_prompt())} chars")
    results = []
    for i, q in enumerate(QUESTIONS, 1):
        r = run_one(i, q)
        results.append(r)
    print("\n" + "="*72 + "\nSUMMARY\n" + "="*72)
    for i, r in enumerate(results, 1):
        ok = "ANS" if r["answer"] else " — "
        print(f"  Q{i}: calls={len(r['calls']):2d} time={r['sec']:5.1f}s {ok}")
    open("/tmp/smoke_results.json","w",encoding="utf-8").write(
        json.dumps(results, ensure_ascii=False, indent=2))
