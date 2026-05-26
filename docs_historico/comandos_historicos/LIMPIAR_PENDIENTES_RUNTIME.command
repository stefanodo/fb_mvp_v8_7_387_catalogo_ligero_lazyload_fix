#!/bin/bash
set -euo pipefail
RUNTIME_DIR="${HOME}/Documents/F&B_MAC_RUNTIME"
DB="${RUNTIME_DIR}/fb_mvp_v8.db"
if [ ! -f "$DB" ]; then
  echo "No existe la base local en ${DB}"
  exit 0
fi
python3 - "$DB" "$RUNTIME_DIR" <<'PY'
import sqlite3, sys, shutil, os
from pathlib import Path
db = Path(sys.argv[1]); runtime = Path(sys.argv[2])
conn = sqlite3.connect(db)
cur = conn.cursor()
ids = [r[0] for r in cur.execute("SELECT id FROM receipts WHERE status='PENDING'").fetchall()]
for rid in ids:
    try:
        ph_rows = cur.execute("SELECT file_path FROM receipt_photos WHERE receipt_id=?", (rid,)).fetchall()
        for (file_path,) in ph_rows:
            try:
                fp = runtime / "uploads" / file_path
                if fp.exists():
                    fp.unlink()
            except Exception:
                pass
        cur.execute("DELETE FROM receipt_ocr_lines WHERE ocr_run_id IN (SELECT id FROM receipt_ocr_runs WHERE receipt_id=?)", (rid,))
        cur.execute("DELETE FROM receipt_ocr_runs WHERE receipt_id=?", (rid,))
        cur.execute("DELETE FROM receipt_lines WHERE receipt_id=?", (rid,))
        cur.execute("DELETE FROM receipt_photos WHERE receipt_id=?", (rid,))
        cur.execute("DELETE FROM receipts WHERE id=? AND status='PENDING'", (rid,))
    except Exception:
        pass
conn.commit()
conn.close()
print(f"Pendientes borrados: {len(ids)}")
PY
echo "Limpieza terminada."
