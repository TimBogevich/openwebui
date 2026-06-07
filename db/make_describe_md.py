# -*- coding: utf-8 -*-
"""Dump describe() output for all tables into a clean .md file."""
import os, re

raw = open('C:/Users/Iskandar/Desktop/describe_dump_raw.txt', encoding='utf-8').read()
blocks = raw.split('---END---')

lines = []
lines.append('# Live describe() output for all tables')
lines.append('')
lines.append('**Generated:** 2026-06-07')
lines.append('**Source:** gcu-mcp container (production state)')
lines.append('')
lines.append('This is exactly what the model sees when it calls `describe(table)` in the live MCP server.')
lines.append('All info read live from PostgreSQL — no hardcoded data, only column comments and live samples.')
lines.append('')
lines.append('## Table of Contents')
lines.append('')

tables = []
for b in blocks:
    m = re.search(r'=== TABLE: (\w+) ===', b)
    if m:
        tables.append(m.group(1))

for t in tables:
    lines.append(f'- [{t}](#{t.lower()})')
lines.append('')
lines.append('---')
lines.append('')

for b in blocks:
    m = re.search(r'=== TABLE: (\w+) ===', b)
    if not m: continue
    tbl = m.group(1)
    parts = b.split('===')
    body = parts[2].strip() if len(parts) > 2 else b.strip()

    lines.append(f'## {tbl}')
    lines.append('')
    lines.append('```')
    lines.append(body.strip())
    lines.append('```')
    lines.append('')
    lines.append('---')
    lines.append('')

out_path = 'C:/Users/Iskandar/Desktop/describe_all_tables.md'
open(out_path, 'w', encoding='utf-8').write('\n'.join(lines))
print('Saved:', out_path)
print('Size:', os.path.getsize(out_path), 'bytes')
print('Tables included:', len(tables))
print()
print('Tables:')
for t in tables: print(f'  - {t}')
