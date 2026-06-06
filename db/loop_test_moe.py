import json, urllib.request, psycopg2

LM = "http://host.docker.internal:1234/v1/chat/completions"
PG = dict(host="postgres", dbname="postgres", user="postgres", password="Gcu2026!", port=5432)
SYS = ("Ты аналитик данных РЖД. Есть Postgres-представление gtsu со столбцами: "
       "report_date (date), зона (текст: 'красная'/'жёлтая'/'зелёная'), section_title, indicator, факт_сутки. "
       "Для ответа ОБЯЗАТЕЛЬНО вызывай инструмент query_gcu с SQL. Не пиши SQL текстом. "
       "После результата дай краткий ответ числом.")
TOOLS = [{"type":"function","function":{
    "name":"query_gcu","description":"read-only SQL SELECT к Postgres (gtsu).",
    "parameters":{"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}}]

def lm(messages):
    body=json.dumps({"model":"qwen3.6-35b-a3b","messages":messages,"tools":TOOLS,
                     "temperature":0.2,"stream":False}).encode()
    req=urllib.request.Request(LM,data=body,headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=240))["choices"][0]

conn=psycopg2.connect(**PG); conn.autocommit=True
def run_sql(sql):
    try:
        cur=conn.cursor(); cur.execute(sql)
        rows=cur.fetchall(); cur.close()
        return json.dumps(rows, ensure_ascii=False, default=str)[:500]
    except Exception as e:
        conn.rollback(); return "ERROR: "+str(e)[:300]

msgs=[{"role":"system","content":SYS},
      {"role":"user","content":"Сколько показателей в красной зоне на 1 марта 2022 года?"}]
for turn in range(1,6):
    ch=lm(msgs); m=ch["message"]; fr=ch["finish_reason"]
    print(f"--- turn {turn}: finish={fr}")
    if m.get("tool_calls"):
        msgs.append(m)
        for tc in m["tool_calls"]:
            sql=json.loads(tc["function"]["arguments"]).get("sql","")
            print("   SQL:",sql)
            res=run_sql(sql); print("   RES:",res[:200])
            msgs.append({"role":"tool","tool_call_id":tc["id"],"content":res})
        continue
    print("   FINAL ANSWER:",(m.get("content") or "")[:800]); break
