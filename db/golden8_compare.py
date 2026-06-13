# -*- coding: utf-8 -*-
"""Run the 8 golden questions through the live agent (single session, relying on
the server's own per-question TTL reset), capture FULL answers, and emit an HTML
report comparing each answer to the golden reference text from the docx.

Runs inside gcu-mcp. Needs /tmp/live_prompt.txt. Writes /tmp/golden8_report.html
and /tmp/golden8_results.json."""
import sys, json, time, urllib.request, os, html
sys.path.insert(0, "/app")
import mcp_postgres_server as S

LM = "http://host.docker.internal:1234/v1/chat/completions"
MODEL = os.environ.get("TEST_MODEL", "qwen3.6-35b-a3b-mtp")
PROMPT = open("/tmp/live_prompt.txt", encoding="utf-8").read()
MAX_TURNS = 14

# 8 self-contained questions (expanded from the docx 4-question chain) + the
# golden reference text (key facts) from the docx for side-by-side comparison.
ITEMS = [
 dict(q="Проанализируй выполнение показателя «Доля грузовых отправок в груженых вагонах, доставленных в срок» (показатель 2.1) на 12 марта 2026 за все три периода — сутки, с начала месяца, с начала года.",
   gold="Сутки 96,5% (ниже плана 2,5 п.п., ниже 2025 на 0,7). Месяц 95,8% (ниже плана 3,2, ниже 2025 на 1,4). Год 98,2% (ниже плана 0,8, выше 2025 на 2). Красная зона риска по всем трём периодам. (источник Доклад СКИМ ОД, срок доставки п.2.1)"),
 dict(q="Какие основные причины и факторы повлияли на невыполнение этого показателя? Приведи структуру задержанных поездов по кодам причин (итог по сети).",
   gold="Невыполнение обусловлено отказами техсредств, ограничениями пропускной/перерабатывающей способности, нарушениями технологии, внешними факторами (грузополучатели, порты). Задержано 475 поездов; коды: 1=152, 5=97, 2=76, 43=59, 22=27, 21=22."),
 dict(q="Приведи цифры по неэффективному использованию перерабатывающей способности припортовых терминалов на 12.03.2026: итог по сети и худшие станции.",
   gold="Выгрузка 17 119 ваг при перерабатывающей способности 31 271 ваг. Худшие: Находка-Восточная 1399/2587, Ванино 1200/1669, Лужская 4299/6332, Автово 919/1928, Вышестеблиевская 1659/3105, Новороссийск 1274/2803. (источник справки припортовых станций ДВОСТ/ОКТ/СКАВ)"),
 dict(q="Какова техническая и участковая скорость по сети на 12.03.2026 и где наибольшее невыполнение?",
   gold="Техническая по сети 43,3 км/ч (выше плана 0,4, ниже 2025 на 0,7); невыполнение Свердловская -3,1, Западно-Сибирская -1,7. Участковая по сети 38,0 км/ч (ниже плана 0,5%, ниже 2025 на 2,3%); невыполнение Свердловская -4,8, Западно-Сибирская -2,1, Красноярская -1,1."),
 dict(q="Проанализируй работу важнейших сортировочных станций на 12.03.2026: где наибольшее превышение простоя транзитного вагона с переработкой.",
   gold="Юдино (ГОРЬК) 56,11 ч при норме 19, парк 2794/1722; Дема (КБШ) 37,75/13,48, 3655/2650; Пермь-Сорт (СВЕРД) 39,49/17, 3822/3400; Кочетовка (ЮВОСТ) 39,05/18, 3919/3200; Агрыз (ГОРЬК) 35,34/17,8; Тайшет (ВСИБ) 31,72/18,7."),
 dict(q="Дай характеристику отказов техсредств 1-2 категории на 12.03.2026: всего по сети, динамика к 2025, по комплексам.",
   gold="234 отказа (+32,2% к 2025), продолжительность 306,77 ч (+72,05%). Задержано 585 грузовых поездов. Наибольшее в локомотивном (124) и инфраструктурном (67) комплексах. (источник КАСАНТ)"),
 dict(q="Сколько отставленных груженых поездов на сети на 12.03.2026, по каким дорогам больше всего и по кодам ответственности РЖД?",
   gold="475 поездов. Дороги: Северо-Кавказская 84, Красноярская 54, Дальневосточная 51. По ответственности РЖД 123: код 43=59, код 21=22, код 22=27; по независящим код 1=152. (источник справка о задержанных)"),
 dict(q="Предложи управленческие решения по вводу показателя доставки в срок в целевое значение.",
   gold="Повышение качества планирования поездной работы; усиление контроля за продвижением вагонопотоков; приоритетность подъёма отставленных; адресная работа со станциями с перепростоями; взаимодействие с грузополучателями/портами; повышение пропускной/перерабатывающей способности; устранение ограничений скорости; повышение надёжности техсредств."),
]

TOOLS = [
 {"type":"function","function":{"name":"gcu-postgres_describe","description":(S.describe.__doc__ or"")[:300],"parameters":{"type":"object","properties":{"table":{"type":"string"}}}}},
 {"type":"function","function":{"name":"gcu-postgres_find_indicator","description":(S.find_indicator.__doc__ or"")[:400],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"}},"required":["query"]}}},
 {"type":"function","function":{"name":"gcu-postgres_query","description":(S.query.__doc__ or"")[:200],"parameters":{"type":"object","properties":{"sql":{"type":"string"}},"required":["sql"]}}},
 {"type":"function","function":{"name":"gcu-postgres_search_knowledge","description":(S.search_knowledge.__doc__ or"")[:250],"parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer"},"collection":{"type":"string"}},"required":["query"]}}},
]

def call(msgs):
    body=json.dumps({"model":MODEL,"messages":msgs,"tools":TOOLS,"temperature":0.2,"stream":False}).encode()
    req=urllib.request.Request(LM,data=body,headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=360))["choices"][0]

def dispatch(name,a):
    if "find_indicator" in name: return S.find_indicator(a.get("query",""),k=a.get("k",5))
    if "describe" in name: return S.describe(a.get("table",""))
    if "_query" in name: return S.query(a.get("sql",""))
    if "search_knowledge" in name: return S.search_knowledge(a.get("query",""),k=a.get("k",3),collection=a.get("collection",""))
    return "unknown"

msgs=[{"role":"system","content":PROMPT}]
results=[]
for qi,it in enumerate(ITEMS,1):
    if qi>1: time.sleep(S._NEWQ_GAP_S+3)   # trigger the server's per-question TTL reset
    msgs.append({"role":"user","content":it["q"]})
    calls=[]; t0=time.time()
    for turn in range(MAX_TURNS):
        ch=call(msgs); m=ch["message"]
        if m.get("tool_calls"):
            msgs.append(m)
            for tc in m["tool_calls"]:
                try: args=json.loads(tc["function"]["arguments"])
                except: args={}
                name=tc["function"]["name"]
                res=dispatch(name,args)
                calls.append(name.split("_")[-1])
                msgs.append({"role":"tool","tool_call_id":tc["id"],"content":str(res)[:1900]})
            continue
        ans=m.get("content") or ""
        msgs.append({"role":"assistant","content":ans})
        results.append(dict(q=it["q"],gold=it["gold"],answer=ans,calls=calls,sec=round(time.time()-t0,1)))
        print("Q%d ANS %d calls %.1fs"%(qi,len(calls),time.time()-t0),flush=True)
        break
    else:
        results.append(dict(q=it["q"],gold=it["gold"],answer=None,calls=calls,sec=round(time.time()-t0,1)))
        print("Q%d CAP"%qi,flush=True)
    json.dump(results,open("/tmp/golden8_results.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)

# ---------- HTML report ----------
def esc(s): return html.escape(s or "")
ans=sum(1 for r in results if r["answer"])
cards=[]
for i,r in enumerate(results,1):
    cited = bool(r["answer"]) and 'источник' in (r["answer"] or '').lower()
    redz  = bool(r["answer"]) and 'красн' in (r["answer"] or '').lower()
    chips=[]
    if cited: chips.append('<span class="chip ok">ссылка на источник</span>')
    if redz:  chips.append('<span class="chip ok">красная зона</span>')
    tools=" → ".join(r["calls"])
    cards.append(
     '<div class="card"><div class="qh">Вопрос %d</div><div class="q">%s</div>'
     '<div class="meta">%d вызовов · %ss · %s</div>'
     '<div class="cols"><div class="col"><div class="lbl gold">ЭТАЛОН (из файла)</div><pre>%s</pre></div>'
     '<div class="col"><div class="lbl ai">ОТВЕТ МОДЕЛИ</div><pre>%s</pre></div></div>'
     '<div class="tools">инструменты: %s</div></div>'
     %(i,esc(r["q"]),len(r["calls"]),r["sec"],"".join(chips),esc(r["gold"]),
       esc(r["answer"]) if r["answer"] else "<i>нет ответа (turn-cap)</i>",esc(tools)))

CSS=("body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f4f5f7;color:#1a1a1a}"
 "header{background:#c8102e;color:#fff;padding:18px 26px}header h1{margin:0;font-size:21px}"
 ".sub{opacity:.9;font-size:13px;margin-top:3px}.wrap{padding:18px 26px;display:grid;gap:16px}"
 ".card{background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 1px 4px rgba(0,0,0,.08)}"
 ".qh{font-size:12px;color:#c8102e;font-weight:700}.q{font-weight:600;margin:3px 0 8px;font-size:15px}"
 ".meta{font-size:12px;color:#777;margin-bottom:10px}.chip{font-size:11px;padding:2px 8px;border-radius:20px;margin-left:6px}"
 ".chip.ok{background:#e8f5e9;color:#2e7d32;border:1px solid #a5d6a7}"
 ".cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:900px){.cols{grid-template-columns:1fr}}"
 ".col{background:#fafafa;border-radius:8px;padding:10px;border:1px solid #eee}"
 ".lbl{font-size:11px;font-weight:700;margin-bottom:6px;padding:2px 6px;border-radius:4px;display:inline-block}"
 ".lbl.gold{background:#fff3e0;color:#e65100}.lbl.ai{background:#e3f2fd;color:#1565c0}"
 "pre{white-space:pre-wrap;font-size:12.5px;margin:0;line-height:1.45;max-height:420px;overflow:auto}"
 ".tools{font-family:ui-monospace,monospace;font-size:11px;color:#0366d6;margin-top:8px}")
doc=('<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Сравнение: 8 эталонных вопросов</title>'
 '<style>%s</style></head><body><header><h1>ЦГЦУ — сравнение ответов модели с эталоном (8 вопросов)</h1>'
 '<div class="sub">%s · ответили %d/8 · %s</div></header><div class="wrap">%s</div></body></html>'
 %(CSS,esc(MODEL),ans,time.strftime("%Y-%m-%d %H:%M"),"".join(cards)))
open("/tmp/golden8_report.html","w",encoding="utf-8").write(doc)
print("\n=== %d/8 answered. report: /tmp/golden8_report.html ==="%ans)
