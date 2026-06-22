# -*- coding: utf-8 -*-
"""Score the golden-40 live answers against the Claude-VERIFIED key
(GOLDEN_40_ANSWERS_VERIFIED.md values). Runs on host. Reads golden40_answers.json.

Each question: either expected NUMERIC values that MUST appear, OR it's a
REFUSAL question where the correct answer says 'нет данных'/'отсутств'.
Reports per-question PASS/PARTIAL/FAIL and whether the post-processor helped."""
import json, re, sys

ANS = json.load(open(sys.argv[1] if len(sys.argv)>1 else "golden40_answers.json", encoding="utf-8"))
D = {x["n"]: x for x in ANS}

def norm(s):
    return re.sub(r"\s","",(s or "")).replace(" ","").replace(" ","").lower()

# expected[q] = list of required substrings (numbers/words). REFUSAL[q]=True → must say no-data.
EXPECT = {
 1: ["98,3","98,36"],                      # доля в срок апрель: day 98,335 / month 98,364
 2: ["погрузк"],                            # qualitative; погрузка by class
 4: ["30"],                                 # доля портов ДВ ≈30%
 5: ["290","5"],                            # травматизм граждане 290 / работники 5
 6: ["9159","8727"],                        # грузооборот
 7: ["827"],                                # начисленная выручка 827,091
 8: ["37,7","38,1"],                        # участковая
 9: ["4128","4133"],                        # средний вес
 10: ["106","1194"],                        # отказы 1,2 кат=106 / 3 кат=1194
 11: ["3279","3169"],                       # погрузка 1-5 апр
 13: ["3 155,5","3155,5","1,4","1,9"],      # comment погрузка
 14: ["2499","приказ"],                     # управленческое решение
 15: ["98,3"],                              # red zone срок доставки
 22: ["61,5"],                              # расписание 15.04
 25: ["37 520","37520"],                    # опоздания month
 26: ["548,38","548,4"],                    # персонал на местах
 27: ["548,38","543,55","4,83"],            # 01 vs 17
 30: ["120,81","53,96","23,19"],            # отсутствуют + причины
 31: ["23,19"],                             # больничный
 32: ["53,96"],                             # отпуск
 33: ["100,56"],                            # укомплект
 34: ["13,33"],                             # командировка
 35: ["670,65"],                            # списочная
 36: ["фирменного транспортного"],          # ЦФТО
 38: ["фактор"],                            # 8 факторов
 40: ["88","47"],                           # red zone 88 vs 47
}
# Questions where the CORRECT answer is a refusal (data absent at that granularity)
REFUSAL = {3, 12, 17, 19, 20, 21, 23, 24, 28, 29}
# (Q12,17 partial-data; Q18,37 nuanced — handled as soft)
SOFT = {18, 37, 39}  # acceptable if mentions the right entities; not auto-graded strictly

REFUSAL_WORDS = ["нет данных","отсутств","не предусмотрен","нельзя","невозможно",
                 "не содержит","нет разбивки","нет такого","не найден","отсутствуют",
                 "только 12.03","только за 12","данные за"]

def is_refusal(ans):
    n = norm(ans)
    return any(norm(w) in n for w in REFUSAL_WORDS)

print("="*86)
print("GOLDEN-40 SCORE vs Claude-verified key (GOLDEN_40_ANSWERS_VERIFIED.md)")
print("="*86)
P=F=R_ok=R_bad=CAP=0
for q in range(1,41):
    x=D.get(q,{})
    raw=x.get("answer") or ""
    if raw in ("<TURN-CAP>","") or raw.startswith("<ERROR"):
        print("Q%-2d  [НЕТ ОТВЕТА — CAP/ERROR]"%q); CAP+=1; continue
    n=norm(raw)
    if q in REFUSAL:
        if is_refusal(raw):
            print("Q%-2d  REFUSAL ✔ (корректно «нет данных»)"%q); R_ok+=1
        else:
            print("Q%-2d  REFUSAL ✘ — должен был отказать, но дал ответ (риск галлюцинации)"%q); R_bad+=1
        continue
    if q in SOFT:
        print("Q%-2d  [SOFT — проверить вручную]"%q); continue
    exp = EXPECT.get(q)
    if not exp:
        print("Q%-2d  [нет ключа]"%q); continue
    hits=[v for v in exp if norm(v) in n]
    if len(hits)==len(exp):
        print("Q%-2d  PASS  (%s)"%(q, ", ".join(exp))); P+=1
    else:
        miss=[v for v in exp if norm(v) not in n]
        print("Q%-2d  FAIL/partial — нет: %s"%(q, ", ".join(miss))); F+=1

print("="*86)
print("ЧИСЛОВЫЕ: %d PASS / %d FAIL  |  ОТКАЗЫ: %d верных / %d пропущенных  |  CAP/нет ответа: %d"%(P,F,R_ok,R_bad,CAP))
pp = sum(1 for x in ANS if x.get("pp_changed"))
print("Пост-процессор изменил ответ в %d из 40 вопросов"%pp)
