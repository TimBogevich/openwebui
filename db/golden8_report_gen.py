# -*- coding: utf-8 -*-
"""Generate the final HTML report from db/golden8_final.json (8 merged results)."""
import json, html, re, io
GOLD = {
 "Q1":"Сутки 96,5% (-2,5 п.п. план, -0,7 к 2025). Месяц 95,8% (-3,2/-1,4). Год 98,2% (-0,8/+2). Красная зона по всем трём периодам.",
 "Q2":"475 поездов. Коды: 1=152, 5=97, 2=76, 43=59, 22=27, 21=22.",
 "Q3":"Выгрузка 17 119 при способности 31 271. Худшие: Находка-Восточная 1399/2587, Ванино 1200/1669, Лужская 4299/6332, Автово 919/1928, Вышестеблиевская 1659/3105, Новороссийск 1274/2803.",
 "Q4":"Техническая сеть 43,3 (+0,4); невыполн. Свердл -3,1, ЗапСиб -1,7. Участковая сеть 38,0; Свердл -4,8, ЗапСиб -2,1, Краснояр -1,1.",
 "Q5":"Юдино 56,11ч (норма 19); Дема 37,75/13,48; Пермь-Сорт 39,49/17; Кочетовка 39,05/18; Тайшет 31,72/18,7.",
 "Q6":"234 отказа (+32,2%), продолжительность 306,77 ч (+72,05%). Задержано 585 поездов. Локомотивный 124, инфраструктурный 67.",
 "Q7":"475 поездов. Дороги: Северо-Кавказская 84, Красноярская 54, Дальневосточная 51. По ответственности РЖД: код 43=59, 21=22, 22=27, код 1=152.",
 "Q8":"Повышение качества планирования; контроль продвижения вагонопотоков; приоритет подъёма отставленных; работа с грузополучателями/портами; пропускная способность; устранение ограничений скорости.",
}
d=json.load(open('db/golden8_final.json',encoding='utf-8'))
def esc(s): return html.escape(s or "")
cards=[]
for i,r in enumerate(d,1):
    tag=r.get('tag','Q%d'%i)
    a=r.get('answer') or ""
    emoji=re.findall(r'[\U0001F300-\U0001FAFF☀-➿]',a)
    tbls=[t for t in ['spravki_','load_fact','row_level','day_fact','delay_code','month_fact'] if t in a]
    chips=[]
    chips.append('<span class="chip ok">ответ ✓</span>' if a else '<span class="chip bad">нет ответа</span>')
    chips.append('<span class="chip %s">эмодзи: %s</span>'%('bad' if emoji else 'ok',(''.join(emoji[:4]) if emoji else 'нет')))
    chips.append('<span class="chip %s">имена таблиц: %s</span>'%('bad' if tbls else 'ok',(','.join(tbls) if tbls else 'нет')))
    tools=" → ".join(r.get('calls',[]))
    cards.append('<div class="card"><div class="qh">%s</div><div class="q">%s</div><div class="meta">%d вызовов · %s</div>'
        '<div class="cols"><div class="col"><div class="lbl gold">ЭТАЛОН (из docx)</div><pre>%s</pre></div>'
        '<div class="col"><div class="lbl ai">ОТВЕТ МОДЕЛИ</div><pre>%s</pre></div></div>'
        '<div class="tools">инструменты: %s</div></div>'
        %(tag,esc(r['q']),len(r.get('calls',[])),"".join(chips),esc(GOLD.get(tag,"")),esc(a) if a else "<i>нет ответа</i>",esc(tools)))
CSS=("body{font-family:Segoe UI,Roboto,sans-serif;margin:0;background:#f4f5f7}header{background:#c8102e;color:#fff;padding:18px 26px}"
 "header h1{margin:0;font-size:20px}.sub{opacity:.9;font-size:13px}.wrap{padding:18px 26px;display:grid;gap:16px}"
 ".card{background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}.qh{color:#c8102e;font-weight:700;font-size:12px}"
 ".q{font-weight:600;margin:3px 0 8px}.meta{font-size:12px;color:#777;margin-bottom:10px}"
 ".chip{font-size:11px;padding:2px 8px;border-radius:20px;margin-right:6px}.chip.ok{background:#e8f5e9;color:#2e7d32;border:1px solid #a5d6a7}"
 ".chip.bad{background:#ffebee;color:#b71c1c;border:1px solid #ef9a9a}.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}"
 "@media(max-width:900px){.cols{grid-template-columns:1fr}}.col{background:#fafafa;border-radius:8px;padding:10px;border:1px solid #eee}"
 ".lbl{font-size:11px;font-weight:700;margin-bottom:6px;padding:2px 6px;border-radius:4px;display:inline-block}"
 ".lbl.gold{background:#fff3e0;color:#e65100}.lbl.ai{background:#e3f2fd;color:#1565c0}"
 "pre{white-space:pre-wrap;font-size:12.5px;margin:0;line-height:1.45;max-height:440px;overflow:auto}"
 ".tools{font-family:monospace;font-size:11px;color:#0366d6;margin-top:8px}")
ans=sum(1 for x in d if x.get('answer'))
doc='<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Тест 8 экспертных вопросов</title><style>%s</style></head><body>'%CSS
doc+='<header><h1>ЦГЦУ — тест 8 экспертных вопросов (эталон vs модель)</h1><div class="sub">qwen3.6-35b-a3b-mtp · ответили %d/8 · проверка фактов + стиля</div></header>'%ans
doc+='<div class="wrap">'+"".join(cards)+'</div></body></html>'
io.open('db/golden8_report.html','w',encoding='utf-8').write(doc)
print('wrote db/golden8_report.html (%d/8 answered)'%ans)
