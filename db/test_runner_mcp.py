# -*- coding: utf-8 -*-
"""57-question runner for gcu-mcp container.
sys.path=/ (mcp_postgres_server.py is at /mcp_postgres_server.py)
Writes /tmp/test_results_47opus.json"""
import json, time, urllib.request, sys, os, re

# mcp_postgres_server.py is at /app/mcp_postgres_server.py on gcu-mcp
import sys
# Ensure /app takes priority (python prepends script dir to sys.path)
for p in ["/app"]:
    if p not in sys.path:
        sys.path.insert(0, p)
import mcp_postgres_server as S

LM = "http://host.docker.internal:1234/v1/chat/completions"
MODEL = os.environ.get("TEST_MODEL", "huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated-mtp")
TIMEOUT = 360
MAX_TURNS = 10

def get_prompt():
    return open("/tmp/live_prompt.txt", encoding="utf-8").read()

TOOLS = [
    {"type":"function","function":{
        "name": "gcu-postgres_describe",
        "description": (S.describe.__doc__ or "")[:300],
        "parameters": {"type":"object","properties":{"table":{"type":"string"}}}}},
    {"type":"function","function":{
        "name": "gcu-postgres_find_indicator",
        "description": (S.find_indicator.__doc__ or "")[:400],
        "parameters": {"type":"object","properties":{
            "query":{"type":"string"},"k":{"type":"integer"}},"required":["query"]}}},
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
    return json.load(urllib.request.urlopen(req, timeout=TIMEOUT))["choices"][0]

def dispatch(name, args):
    if "find_indicator" in name:
        return S.find_indicator(args.get("query",""), k=args.get("k",5))
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
    print(f"\n{'='*72}\nQ{num}: {question[:80]}\n{'='*72}", flush=True)
    try:
        S._recent_q.clear()
        S._consec_zero[0] = 0
        S._find_calls[0] = 0
        S._describe_calls[0] = 0
        S._query_calls[0] = 0
        S._tool_calls[0] = 0
    except Exception:
        pass
    sys_prompt = get_prompt()
    msgs = [{"role":"system","content":sys_prompt},
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
                try:
                    args = json.loads(tc["function"]["arguments"])
                except: args = {}
                primary = list(args.values())[0] if args else ""
                snippet = str(primary)[:90].replace("\n"," ")
                print(f"  [t{turn+1}] -> {name}({snippet})", flush=True)
                tool_calls.append({"name":name, "args":args})
                result = dispatch(name, args)
                if not isinstance(result, str):
                    result = str(result)
                msgs.append({"role":"tool",
                             "tool_call_id": tc["id"],
                             "content": result[:1800]})
            continue
        content = m.get("content") or ""
        sec = round(time.time()-t0, 1)
        ans_short = content[:200].replace("\n"," ")
        print(f"  [{len(tool_calls)} calls, {sec}s] {ans_short}", flush=True)
        return {"q":question, "calls":tool_calls,
                "answer":content, "sec":sec, "err":None}
    sec = round(time.time()-t0, 1)
    print(f"  [CAP HIT {sec}s]", flush=True)
    return {"q":question,"calls":tool_calls,"answer":None,"sec":sec,"err":"turn-cap"}

# Load questions from /tmp/questions.py
import importlib.util
spec = importlib.util.spec_from_file_location("q", "/tmp/questions.py")
qmod = importlib.util.module_from_spec(spec); spec.loader.exec_module(qmod)
QUESTIONS = qmod.QUESTIONS

if __name__ == "__main__":
    print(f"MODEL = {MODEL}", flush=True)
    print(f"prompt len = {len(get_prompt())} chars", flush=True)
    print(f"running {len(QUESTIONS)} questions", flush=True)
    results = []
    for i, q in enumerate(QUESTIONS, 1):
        r = run_one(i, q)
        results.append(r)
        open("/tmp/test_results_47opus.json","w",encoding="utf-8").write(
            json.dumps(results, ensure_ascii=False, indent=2))
    print("\n\n" + "="*72)
    print("SUMMARY")
    print("="*72)
    for i, r in enumerate(results, 1):
        ok = "ANS" if r["answer"] else " — "
        print(f"  Q{i:2d}: calls={len(r['calls']):2d} time={r['sec']:5.1f}s {ok} | {r['q'][:55]}")
    open("/tmp/test_results_47opus.json","w",encoding="utf-8").write(
        json.dumps(results, ensure_ascii=False, indent=2))
    print("\nfull log saved to /tmp/test_results_47opus.json")