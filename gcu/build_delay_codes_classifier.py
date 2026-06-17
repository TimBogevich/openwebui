# -*- coding: utf-8 -*-
"""
Build the full classifier of delay reason codes from two source documents:
  1. xlsx «Коды бросаний для справки.xlsx» — compact: code → brief name,
     grouped under responsibility headers (Не на ответственности перевозчика,
     Д/Т/ТР/ДРП/ДИ/НТЭ/ДМВ/ДМ/С/ТЦФТО/Прочие).
  2. docx «Doc5.docx» — Распоряжение ОАО РЖД №85/р от 20.01.2025: 3-column
     classifier table (N п/п | Код | Полное описание).

Output: idempotent SQL → /tmp/delay_codes_full.sql (copied to db/).

Codes 1-6 are NOT РЖД's responsibility (Грузоотправитель/Грузополучатель/
Третьи лица); 11+ are РЖД, split by directorate (ЦД, ЦТ, ЦТВР, ЦДРП, ЦДИ,
ТЭ, ЦМВПС, ЦДС, ЦСС, ЦФТО); 91-95 are Прочие/Третьи лица.

Run inside gcu-upload (has openpyxl):
  docker cp xlsx gcu-upload:/tmp/codes.xlsx
  docker cp docx gcu-upload:/tmp/doc5.docx
  docker cp gcu/build_delay_codes_classifier.py gcu-upload:/tmp/build.py
  docker exec gcu-upload python3 /tmp/build.py
  docker cp gcu-upload:/tmp/delay_codes_full.sql db/delay_reason_codes_full.sql
  docker exec -i gcu-postgres psql -U postgres -d postgres < db/delay_reason_codes_full.sql
"""
import openpyxl, zipfile, re

CODE_RESP = {
    '1': ('Грузоотправитель/Грузополучатель/Оператор ПС', 'Грузополучатель'),
    '2': ('Третьи лица / Сторонние организации', 'ЦД, ЦСС'),
    '3': ('Третьи лица / Сторонние организации', ''),
    '4': ('Грузоотправитель/Грузополучатель/Оператор ПС', 'Грузоотправитель, Оператор ПС'),
    '5': ('Грузоотправитель/Грузополучатель/Оператор ПС', 'Грузополучатель'),
    '6': ('Грузоотправитель/Грузополучатель/Оператор ПС', 'Грузополучатель'),
    '91': ('Третьи лица / Сторонние организации', ''),
    '92': ('Перевозчик', 'ЦД, ЦСС'),
    '93': ('Третьи лица / Сторонние организации', ''),
    '94': ('Третьи лица / Сторонние организации', ''),
    '95': ('Третьи лица / Сторонние организации', ''),
}
CODE_NOTES = {
    '5': 'Платная услуга по договору о временном размещении подвижного состава; при корректном оформлении документов на нарушение срока доставки не влияет.',
    '1': 'Учитывается как одна из причин нарушения срока доставки (методика 2040/р).',
}
# Order from MORE-specific to LESS-specific — earlier match wins.
GROUPS = [
    ('ремонту тягового',               'Перевозчик', 'ЦТВР'),   # ТР — must come BEFORE «тяги»
    ('ремонту пути',                   'Перевозчик', 'ЦДРП'),   # ДРП
    ('моторвагонного',                 'Перевозчик', 'ЦМВПС'),  # ДМВ
    ('терминально-складским',          'Перевозчик', 'ЦДС'),    # ДМ
    ('дирекции связи',                 'Перевозчик', 'ЦСС'),    # С (sometimes column 2)
    ('фирменного транспортного',       'Перевозчик', 'ЦФТО'),   # ТЦФТО
    ('энергообеспечению',              'Перевозчик', 'ТЭ'),     # НТЭ
    ('инфраструктуры',                 'Перевозчик', 'ЦДИ'),    # ДИ
    ('дирекция управления движением',  'Перевозчик', 'ЦД'),     # Д
    ('дирекция тяги',                  'Перевозчик', 'ЦТ'),     # Т
    ('не на ответственности',          'Грузоотправитель/Грузополучатель/Оператор ПС', ''),
    ('прочие',                         'Третьи лица / Сторонние организации', ''),
]

# ── 1. xlsx ───────────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook('/tmp/codes.xlsx', data_only=True)
cur_resp, cur_units = 'Перевозчик', ''
xlsx = {}
for row in wb.worksheets[0].iter_rows(values_only=True):
    c0 = str(row[0]).strip() if row[0] is not None else ''
    c1 = str(row[1]).strip() if row[1] is not None else ''
    # Group header detection: c0 is empty AND c1 is text (rare layout, e.g. «дирекция связи»),
    # OR c0 is non-digit text (normal layout).
    header_text = ''
    if not c0 and c1 and not c1.isdigit() and len(c1) > 10:
        header_text = c1
    elif c0 and not c0.isdigit() and c0 != 'Код':
        header_text = c0
    if header_text:
        for kw, resp, units in GROUPS:
            if kw in header_text.lower():
                cur_resp, cur_units = resp, units
                break
        continue
    if c0.isdigit() and c1:
        code = str(int(c0))
        resp, units = CODE_RESP.get(code, (cur_resp, cur_units))
        xlsx[code] = {'brief': c1, 'resp': resp, 'units': units, 'note': CODE_NOTES.get(code, '')}
print('xlsx:', len(xlsx), 'codes')

# ── 2. docx — fixed regex: <w:t(?![a-zA-Z]) so we don't match <w:tc>, <w:tbl> ──
xml = zipfile.ZipFile('/tmp/doc5.docx').read('word/document.xml').decode('utf-8')
# correct pattern: only match the actual text element <w:t>, not <w:tc> / <w:tbl> / <w:tr>
TEXT_RE = re.compile(r'<w:t(?![a-zA-Z])[^>]*>(.*?)</w:t>', re.DOTALL)

paras = []
for p in xml.split('</w:p>'):
    txt = ''.join(TEXT_RE.findall(p))
    txt = txt.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').strip()
    paras.append(txt)  # keep empties — table alignment is 3 paragraphs per row

# Find the classifier table and walk through, handling section headers.
# Pattern: each table ROW emits 3 paragraphs (N | Code | Description).
# - Data rows: seq (e.g. "1." or "7.1.") | code (e.g. "01") | description text
# - Section header rows: seq (e.g. "7.") | EMPTY | "Д - дирекция…" (3 paragraphs but
#   the "code" cell is empty so the middle paragraph is the section description repeated).
# After the header table (N п/п | Код | Причины) we read consecutive 3-tuples until
# end of document. Skip any tuple where the code cell is not a 1-2 digit number.
docx = {}
i = 0
# find the header
while i < len(paras) and 'п/п' not in paras[i]:
    i += 1
# advance past "N п/п", "Код", "Причины..." headers
i += 3
# read triplets until we run out
while i + 2 < len(paras):
    seq = paras[i].rstrip('.')
    code_raw = paras[i+1]
    desc = paras[i+2]
    # stop conditions: footer text, references, etc.
    if seq.startswith('УТВЕРЖДЕНЫ') or 'распоряжением' in seq.lower() or 'примечание' in seq.lower():
        break
    # section header row: code_raw is NOT a 1-2 digit code (it's text/empty/the header desc)
    if code_raw.isdigit() and 1 <= len(code_raw) <= 2 and desc and not desc.isdigit():
        code = str(int(code_raw))
        docx[code] = desc
    # always advance by 3 — assume each table row = 3 paragraphs
    i += 3

print('docx:', len(docx), 'codes parsed')
if len(docx) < 10:
    print('  WARNING: few docx codes — showing nearby paras for debug')
    for j, p in enumerate(paras[:50]):
        print(f'  {j}: {repr(p[:60])}')

# ── 3. SQL ────────────────────────────────────────────────────────────────────
def esc(s): return (s or '').replace("'", "''")

rows = []
for code in sorted(xlsx.keys(), key=int):
    d = xlsx[code]
    rows.append(
        "  ('{}', '{}', NULL, '{}', '{}', 'методика №2040/р (Распоряжение №85/р 2025)', '{}', '{}')".format(
            esc(code), esc(d['brief']), esc(d['resp']), esc(d['units']),
            esc(d['note']), esc(docx.get(code, ''))
        )
    )

sql = '\n'.join([
    '-- delay_reason_codes_full.sql',
    '-- Full classifier: xlsx brief names + docx full descriptions (Распоряжение №85/р 2025).',
    '-- Idempotent. Run: docker exec -i gcu-postgres psql -U postgres -d postgres < db/delay_reason_codes_full.sql',
    '',
    'BEGIN;',
    'ALTER TABLE delay_reason_codes ADD COLUMN IF NOT EXISTS full_description text;',
    '',
    'INSERT INTO delay_reason_codes',
    '  (delay_code, reason_name, violation, responsibility, units, source, note, full_description)',
    'VALUES',
    ',\n'.join(rows),
    'ON CONFLICT (delay_code) DO UPDATE SET',
    '  reason_name      = EXCLUDED.reason_name,',
    '  responsibility   = EXCLUDED.responsibility,',
    '  units            = EXCLUDED.units,',
    '  source           = EXCLUDED.source,',
    '  note             = CASE WHEN delay_reason_codes.note IS NOT NULL AND delay_reason_codes.note != \'\'',
    '                         THEN delay_reason_codes.note ELSE EXCLUDED.note END,',
    '  full_description = EXCLUDED.full_description;',
    '',
    'COMMIT;',
])
open('/tmp/delay_codes_full.sql', 'w', encoding='utf-8').write(sql)
print('SQL written:', len(xlsx), 'codes')
# verify a few docx matches
for c in ['1','5','21','43','92']:
    v = docx.get(c, 'MISSING')
    print('  code', c, '->', v[:70])
