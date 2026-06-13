# -*- coding: utf-8 -*-
"""Round-2 stuck-fix: a GLOBAL per-question tool-call budget covering ALL
exploration tools (describe + find_indicator + query), not just query().

Why: the round-1 volume guard only blocked query(). Cap-hit traces (e.g. Q28:
17 calls / 3 queries / 4 guard-hits, still CAP) show the model escaping the
query-block by switching to describe()/find_indicator() and never answering.
This adds a shared budget so once total exploration calls exceed the cap, every
tool returns the same 'answer now' stop — the model cannot dodge it.

Applies by editing gcu/mcp_postgres_server.py in place (idempotent — guarded by
a sentinel). Run: python db/apply_round2_guard.py
"""
import re, io, sys

SRC = "gcu/mcp_postgres_server.py"
SENTINEL = "_TOOL_BUDGET"

code = io.open(SRC, encoding="utf-8").read()
if SENTINEL in code:
    print("[skip] round-2 guard already present")
    sys.exit(0)

# 1) add the shared budget state + helper after the _query_calls block
anchor = "_QVOL_BLOCK = 6   # 7th query -> hard stop"
helper = anchor + '''

# Round-2: GLOBAL exploration budget across ALL tools (describe+find+query).
# The model was escaping the query-only block by switching to describe/find.
# Once total exploration calls exceed _TOOL_BUDGET, every tool returns the same
# hard "answer now" stop so it cannot dodge by changing tool.
_tool_calls = [0]
_TOOL_BUDGET = 9   # ~ describe + find + a few queries; beyond this = wandering
_STUCK_MSG = ("\\u26d4 СТОП: израсходован бюджет обращений к БД по этому вопросу. "
    "Нужные данные уже среди полученных результатов выше. НЕМЕДЛЕННО сформулируй "
    "ОТВЕТ на их основе — не вызывай больше describe/find_indicator/query. "
    "Если одного числа не хватает — дай ответ по имеющимся данным и укажи, чего нет.")

def _budget_check():
    """Increment the global tool budget; return _STUCK_MSG if exceeded, else None."""
    _tool_calls[0] += 1
    if _tool_calls[0] > _TOOL_BUDGET:
        return _STUCK_MSG
    return None'''
code = code.replace(anchor, helper, 1)

# 2) insert a budget check at the top of each tool body (after docstring import)
def inject(code, func_sig, after_line):
    """Insert the budget check right after `after_line` inside func."""
    idx = code.index(func_sig)
    pos = code.index(after_line, idx) + len(after_line)
    guard = ('\n    _stuck = _budget_check()\n'
             '    if _stuck:\n        return _stuck\n')
    return code[:pos] + guard + code[pos:]

# describe(): after its 'import psycopg'
code = inject(code, "def describe(table: str", "\n    import psycopg")
# query(): right after the def line's docstring — insert before _query_calls incr
qpos = code.index("def query(sql: str")
qbody = code.index("    # Query-volume", qpos)
code = code[:qbody] + "    _stuck = _budget_check()\n    if _stuck:\n        return _stuck\n\n" + code[qbody:]
# find_indicator(): after its 'import psycopg'
code = inject(code, "def find_indicator(query: str", "\n    import psycopg")

io.open(SRC, "w", encoding="utf-8").write(code)
print("[ok] round-2 global tool-budget guard applied (_TOOL_BUDGET=9)")
