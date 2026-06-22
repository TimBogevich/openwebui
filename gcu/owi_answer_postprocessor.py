# -*- coding: utf-8 -*-
"""
title: ЦГЦУ Answer Post-Processor
author: gcu-team
version: 1.0.0
description: Детерминированная нормализация ФИНАЛЬНОГО ответа модели (outlet). Чинит то,
  что нельзя гарантировать промптом/комментариями БД: единицы (п.п. vs % vs км/ч),
  орфографию единиц (поездо-часа), типографику. НЕ меняет числа и смысл — только форму.
type: filter
"""

import re
from typing import Optional


class Filter:
    """
    Outlet-only filter. Runs on the assistant's final message text AFTER the model
    has answered, BEFORE it reaches the user. 100% deterministic — does not touch
    the system prompt, does not call the model, does not invent or alter any numbers.

    Fixes (verified against the DB-checked golden answers):
      1. UNITS «п.п.» misused for COUNT growth and for SPEED:
         - «<число> отказ…/поезд… … +N п.п.» → «+N %»  (счётные величины растут в %, не п.п.)
         - «<скорость> … N п.п.» (км/ч контекст) → «N км/ч»
         «п.п.» оставляем там, где речь о ДОЛЯХ/процентных показателях (доля в срок, коэффициент).
      2. ОРФОГРАФИЯ единиц: «поездочас…» → «поездо-час…».
      3. ТИПОГРАФИКА: висячие двойные пробелы, дефис вместо минуса в «- N» перед числом.

    Conservative by design: every rule is anchored on explicit unit words so it cannot
    corrupt unrelated text. If unsure, it leaves the text untouched.
    """

    def __init__(self):
        pass

    # ---- individual, well-anchored transforms ------------------------------

    @staticmethod
    def _fix_pp_for_counts(text: str) -> str:
        """+32,2 п.п. → +32,2 % when the sentence is about a COUNT (отказ/поезд/нарушени/
        случа/окон/ед.) growing/declining to last year. Counts grow in %, not п.п."""
        # Pattern: a count noun appears within ~40 chars before "<sign><num> п.п."
        count_ctx = r"(отказ|поезд|поездо|нарушени|случа|окон|ваг\.|вагон|ед\.|штук)"
        # Count word may appear BEFORE the number ("отказы выросли на 32,2 п.п.")
        # OR AFTER it ("32,2 п.п. отказов"). Handle both, anchored on a count word
        # within ~60 chars so it never touches доля/процентные показатели.
        num_pp = r"[+\-−]?\s?\d+[.,]?\d*\s?п\.п\."
        pat_before = re.compile(r"(?:" + count_ctx + r")[^.;:%]{0,60}?" + num_pp, re.IGNORECASE)
        pat_after  = re.compile(num_pp + r"[^.;:%]{0,30}?(?:" + count_ctx + r")", re.IGNORECASE)
        out = []
        last = 0
        # collect match spans from both patterns, flip the "п.п." inside each
        spans = []
        for m in pat_before.finditer(text):
            spans.append((m.start(), m.end(), "before"))
        for m in pat_after.finditer(text):
            spans.append((m.start(), m.end(), "after"))
        if not spans:
            return text
        spans.sort()
        # merge/skip overlaps
        result = []
        cursor = 0
        for s, e, kind in spans:
            if s < cursor:
                continue
            seg = text[s:e]
            # flip the FIRST п.п. for "after" (number is at seg start) else the LAST.
            if kind == "after":
                seg2 = re.sub(r"п\.п\.", "%", seg, count=1)
            else:
                seg2 = re.sub(r"п\.п\.(?!.*п\.п\.)", "%", seg)  # last occurrence
            result.append(text[cursor:s]); result.append(seg2); cursor = e
        result.append(text[cursor:])
        return "".join(result)

    @staticmethod
    def _fix_pp_for_speed(text: str) -> str:
        """«…км/ч … N п.п.» → «N км/ч». Speed deviations are in км/ч, never п.п.
        Anchored: the same clause must contain «км/ч»."""
        def repl_line(line: str) -> str:
            if "км/ч" not in line:
                return line
            # within a км/ч line, turn "<±num> п.п." into "<±num> км/ч"
            return re.sub(r"([+\-−]?\s?\d+[.,]?\d*)\s?п\.п\.", r"\1 км/ч", line)
        return "\n".join(repl_line(ln) for ln in text.split("\n"))

    @staticmethod
    def _fix_poezdochas(text: str) -> str:
        """«поездочас…» → «поездо-час…» (correct hyphenation)."""
        return re.sub(r"поездочас", "поездо-час", text, flags=re.IGNORECASE)

    @staticmethod
    def _fix_typography(text: str) -> str:
        # collapse accidental double spaces (not at line starts / not in tables)
        text = re.sub(r"(?<=\S)  +(?=\S)", " ", text)
        return text

    def _process(self, text: str) -> str:
        if not text or not isinstance(text, str):
            return text
        original = text
        try:
            text = self._fix_poezdochas(text)
            text = self._fix_pp_for_speed(text)
            text = self._fix_pp_for_counts(text)
            text = self._fix_typography(text)
        except Exception:
            # never break the answer — on any error, return it untouched
            return original
        return text

    # ---- OWI filter hooks ---------------------------------------------------

    async def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """Runs on the final assistant message before display."""
        try:
            msgs = body.get("messages", [])
            for msg in reversed(msgs):
                if msg.get("role") == "assistant" and isinstance(msg.get("content"), str):
                    msg["content"] = self._process(msg["content"])
                    break
        except Exception:
            pass
        return body
