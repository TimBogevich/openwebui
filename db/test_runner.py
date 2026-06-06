# -*- coding: utf-8 -*-
"""
Runs 10 real customer questions through the live MoE via LM Studio + MCP.
Logs every tool call, every result snippet, final answer, latency.
NO interventions — pure observation of what the deployed v2 prompt produces.
"""
import json, time, sqlite3, urllib.request, sys, re

LM = "http://host.docker.internal:1234/v1/chat/completions"
MODEL = "qwen3.6-35b-a3b"
TIMEOUT = 360
MAX_TURNS = 10

# Pull live system prompt from OWI so this matches what real chats use
def get_prompt():
    c = sqlite3.connect("/app/backend/data/webui.db")
    p = json.loads(c.execute(
        "SELECT params FROM model WHERE id=?", (MODEL,)).fetchone()[0])
    return p["system"]

# Mirror real OWI tool names + descriptions
import mcp_postgres_server as S

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
    return json.load(urllib.request.urlopen(req, timeout=TIMEOUT))["choices"][0]

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
    print(f"\n{'='*72}\nQ{num}: {question}\n{'='*72}")
    sys_prompt = get_prompt()
    msgs = [{"role":"system","content":sys_prompt},
            {"role":"user","content":question}]
    t0 = time.time()
    tool_calls = []
    for turn in range(MAX_TURNS):
        try:
            ch = call_lm(msgs)
        except Exception as e:
            print(f"  [LM ERROR turn {turn+1}]: {e}")
            return {"q":question,"calls":tool_calls,"answer":None,"sec":round(time.time()-t0,1),"err":str(e)}
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
                print(f"  [t{turn+1}] -> {name}({snippet})")
                tool_calls.append({"name":name, "args":args})
                result = dispatch(name, args)
                if not isinstance(result, str):
                    result = str(result)
                # truncate so we don't bloat the prompt
                msgs.append({"role":"tool",
                             "tool_call_id": tc["id"],
                             "content": result[:1800]})
            continue
        # final answer
        content = m.get("content") or ""
        sec = round(time.time()-t0, 1)
        print(f"\n  FINAL ({len(tool_calls)} tool calls, {sec}s):")
        print("  " + content[:1800].replace("\n","\n  "))
        return {"q":question, "calls":tool_calls,
                "answer":content, "sec":sec, "err":None}
    sec = round(time.time()-t0, 1)
    print(f"\n  [CAP HIT after {MAX_TURNS} turns, {sec}s] no final answer")
    return {"q":question,"calls":tool_calls,"answer":None,"sec":sec,"err":"turn-cap"}

QUESTIONS = [
    # 1. Simple — should be direct query
    "Сколько показателей в красной зоне 30 апреля 2026 года?",
    # 2. Trend question (multi-day) — should pull a date range
    "Покажи динамику показателя «Доля груз. отправок в груж. вагонах с собл. установл. срока доставки» по дням за апрель 2026 года.",
    # 3. Top-K by breakdown — should JOIN+ORDER BY
    "Какое подразделение допустило больше всего опозданий грузовых поездов в апреле 2026 года?",
    # 4. Per-railway breakdown
    "Назови три дороги с самой высокой скоростью доставки груженых отправок 1 марта 2022 года.",
    # 5. Workforce — uses tested indicator
    "Какова численность персонала на рабочих местах на 1 апреля и 17 апреля 2026 года? Сравни их.",
    # 6. Investment — uses separate table
    "Покажи общие инвестиционные затраты по программе «5 ИНВЕСТИЦИОННАЯ ПРОГРАММА» на 1 марта 2022 (план и факт периода).",
    # 7. Knowledge-base question (тeoretical)
    "Что означает аббревиатура ЦФТО в структуре ОАО РЖД?",
    # 8. Mixed numbers + comments — needs report_comments
    "Покажи комментарий из доклада по показателю «Погрузка общая» на 30 апреля 2026 года.",
    # 9. Counter / cumulative — tests populates awareness
    "Сколько фактов опоздания грузовых поездов накопилось с начала апреля 2026?",
    # 10. Multi-period analysis — full template-style
    "Проанализируй показатель «Доля груз. отправок в груж. вагонах с собл. установл. срока доставки» на 30 апреля 2026: дай факт, отклонения от плана и от прошлого года за все три периода (сутки/месяц/год), укажи зону.",
]

if __name__ == "__main__":
    results = []
    for i, q in enumerate(QUESTIONS, 1):
        r = run_one(i, q)
        results.append(r)
    print("\n\n" + "="*72)
    print("SUMMARY")
    print("="*72)
    for i, r in enumerate(results, 1):
        ok = "ANS" if r["answer"] else "—"
        print(f"  Q{i}: calls={len(r['calls'])} time={r['sec']}s {ok}  | {r['q'][:60]}")
    # save raw json for follow-up
    open("/tmp/test_results.json","w",encoding="utf-8").write(
        json.dumps(results, ensure_ascii=False, indent=2))
    print("\nfull log saved to /tmp/test_results.json")
