# -*- coding: utf-8 -*-
"""Manually re-test 10 failed questions after the policy split."""
import json, time, urllib.request, sys, os
sys.path.insert(0, "/app")
import mcp_postgres_server as S

LM = "http://host.docker.internal:1234/v1/chat/completions"
MODEL = "qwen3.6-35b-a3b"
MAX_TURNS = 10

# Same 10 questions, English-described for tracking
QUESTIONS = [
    (2,  "Филиалы ОАО «РЖД», допустившие максимальное количество задержек в апреле 2026 г."),
    (4,  "Сумма задержек (риск предъявления за просрочку доставки) по всем филиалам ОАО «РЖД» на 12.03.2026."),
    (8,  "Количество задержанных поездов по причине нет локомотива перевозчика (код 22) на 12.03.2026 по дорогам."),
    (17, "Назови три дороги у которых 12 марта 2026 было больше всего задержанных поездов по коду 1 (неприём грузополучателем). Приведи значения для каждой."),
    (19, "Назови топ-3 подразделения ОАО РЖД по числу фактов опоздания грузовых поездов за апрель 2026. Приведи числа нарастающим итогом на 30 апреля."),
    (21, "Какова сумма исков к ОАО РЖД о взыскании пени за просрочку доставки грузов по состоянию на 12 марта 2026 — за месяц и нарастающим?"),
    (30, "Какая дорога показала наибольшую скорость доставки грузовых отправок в груженых вагонах на 1 марта 2022? Покажи топ-3."),
    (38, "Сколько отказов техсредств 1-2 категории зафиксировано на Октябрьской и Свердловской дорогах по суточной справке за 12.03.2026? Сравни с 2025 годом."),
    (40, "Каков процент выполнения расписания грузовых поездов по прибытию на конечную станцию на 12 марта 2026? Разбери все 4 компонента (4.1.1–4.1.4)."),
    (46, "Как менялся процент выполнения расписания по прибытию на конечную станцию в апреле 2026 — покажи значения на 1, 15 и 30 апреля."),
]

def get_prompt():
    return open("/tmp/live_prompt.txt", encoding="utf-8").read()

TOOLS = [
    {"type":"function","function":{
        "name": "gcu-postgres_describe",
        "description": (S.describe.__doc__ or "")[:300],
        "parameters": {"type":"object","properties":{"table":{"type":"string"}}}}},
    {"type":"function","function":{
        "name": "gcu-postgres_query",
        "description": (S.query.__doc__ or "")[:200],
        "parameters": {"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}},
    {"type":"function","function":{
        "name": "gcu-postgres_current_datetime",
        "description": (S.current_datetime.__doc__ or "")[:200],
        "parameters": {"type":"object","properties":{"timezone":{"type":"string"}}}}},
    {"type":"function","function":{
        "name": "gcu-postgres_search_knowledge",
        "description": (S.search_knowledge.__doc__ or "")[:300],
        "parameters": {"type":"object","properties":{
            "query":{"type":"string"},"k":{"type":"integer"},"collection":{"type":"string"}},
            "required":["query"]}}},
]

def call_lm(messages):
    body = json.dumps({"model": MODEL, "messages": messages, "tools": TOOLS,
                       "temperature": 0.2, "stream": False}).encode()
    req = urllib.request.Request(LM, data=body, headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req, timeout=360))["choices"][0]

def dispatch(name, args):
    if "describe" in name:
        return S.describe(args.get("table",""))
    if "_query" in name:
        return S.query(args.get("sql",""))
    if "current_datetime" in name:
        return S.current_datetime(args.get("timezone","Europe/Moscow"))
    if "search_knowledge" in name:
        return S.search_knowledge(args.get("query",""),
                                  k=args.get("k",3),
                                  collection=args.get("collection",""))
    return f"unknown tool: {name}"

def run_one(num, question):
    print(f"\n{'='*72}\nQ{num}: {question[:90]}\n{'='*72}", flush=True)
    S._recent_q.clear()
    msgs = [{"role":"system","content":get_prompt()},
            {"role":"user","content":question}]
    t0 = time.time()
    tool_calls = []
    for turn in range(MAX_TURNS):
        try:
            ch = call_lm(msgs)
        except Exception as e:
            return {"q":question,"calls":tool_calls,"answer":None,
                    "sec":round(time.time()-t0,1),"err":str(e)[:200]}
        m = ch["message"]
        if m.get("tool_calls"):
            msgs.append(m)
            for tc in m["tool_calls"]:
                name = tc["function"]["name"]
                try: args = json.loads(tc["function"]["arguments"])
                except: args = {}
                primary = list(args.values())[0] if args else ""
                snippet = str(primary)[:100].replace("\n"," ")
                print(f"  [t{turn+1}] -> {name}({snippet})", flush=True)
                tool_calls.append({"name":name, "args":args})
                result = dispatch(name, args)
                if not isinstance(result, str): result = str(result)
                msgs.append({"role":"tool",
                             "tool_call_id": tc["id"],
                             "content": result[:1800]})
            continue
        content = m.get("content") or ""
        sec = round(time.time()-t0, 1)
        print(f"  [{len(tool_calls)} calls, {sec}s]", flush=True)
        print(f"  ANSWER: {content[:300]}", flush=True)
        return {"q":question, "calls":tool_calls,
                "answer":content, "sec":sec, "err":None}
    sec = round(time.time()-t0, 1)
    print(f"  [CAP HIT {sec}s]", flush=True)
    return {"q":question,"calls":tool_calls,"answer":None,"sec":sec,"err":"turn-cap"}

if __name__ == "__main__":
    print(f"MODEL = {MODEL}")
    print(f"prompt len = {len(get_prompt())} chars")
    print(f"running {len(QUESTIONS)} retests")
    results = []
    for num, q in QUESTIONS:
        r = run_one(num, q)
        r['orig_q_num'] = num
        results.append(r)
        open("/tmp/retest_10_results.json","w",encoding="utf-8").write(
            json.dumps(results, ensure_ascii=False, indent=2))
    print("\n\n" + "="*72)
    print("SUMMARY")
    print("="*72)
    for r in results:
        ok = "ANS" if r["answer"] else " — "
        print(f"  Q{r['orig_q_num']:2d}: calls={len(r['calls']):2d} time={r['sec']:5.1f}s {ok}")
