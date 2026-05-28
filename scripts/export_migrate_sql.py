#!/usr/bin/env python3
import re
from pathlib import Path
p = Path('backend/migrate.py').read_text()
sqls = []
# Triple-quoted execute blocks
for m in re.finditer(r"cur\.execute\(\s*\"\"\"(.*?)\"\"\"", p, re.S):
    s = m.group(1).strip()
    if s:
        sqls.append(s)
# Single-quoted/double-quoted cur.execute(...) that include CREATE/ALTER/COMMENT
for m in re.finditer(r'cur\.execute\(\s*"([^\"]*(?:CREATE|ALTER|COMMENT|CREATE INDEX|CREATE UNIQUE INDEX|CREATE SEQUENCE|CREATE EXTENSION)[^\"]*)"', p, re.I):
    s = m.group(1).strip()
    if s:
        sqls.append(s)
for m in re.finditer(r"cur\.execute\(\s*'([^']*(?:CREATE|ALTER|COMMENT|CREATE INDEX|CREATE UNIQUE INDEX|CREATE SEQUENCE|CREATE EXTENSION)[^']*)'", p, re.I):
    s = m.group(1).strip()
    if s:
        sqls.append(s)
# Lists for indexes and similar
for m in re.finditer(r'for sql in \[\s*(.*?)\s*\]:', p, re.S|re.I):
    content = m.group(1)
    for mm in re.finditer(r'["\'](CREATE.*?)["\']', content, re.S|re.I):
        s = mm.group(1).strip()
        if s:
            sqls.append(s)

# Filter and dedupe
keep = []
seen = set()
for s in sqls:
    key = '\n'.join([line.strip() for line in s.splitlines() if line.strip()])
    if key and key not in seen:
        seen.add(key)
        keep.append(s)

out = '\n\n'.join(keep)
if not out.strip():
    print('No SQL found in backend/migrate.py')
else:
    # Ensure each block ends with a semicolon for psql execution.
    blocks = []
    for s in keep:
        s = s.strip()
        if not s.endswith(';'):
            s = s + ';'
        blocks.append(s)
    final = '\n\n'.join(blocks)
    Path('tmp_migrate.sql').write_text(final)
    print(f'Wrote {len(keep)} SQL blocks to tmp_migrate.sql')
