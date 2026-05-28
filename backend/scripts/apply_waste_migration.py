#!/usr/bin/env python3
import sys
sys.path.insert(0, 'backend')
from app.core import db

def main():
    conn = db(); cur = conn.cursor()
    stmts = [
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS warehouse_id INTEGER",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS responsible_user_id INTEGER",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS responsible_name TEXT",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS source_type TEXT",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS item_type TEXT",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS article_id INTEGER",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS recipe_id INTEGER",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS item_name_detected TEXT",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS unit TEXT",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS qty_base NUMERIC",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS base_unit TEXT",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS photo_path TEXT",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS voice_text_raw TEXT",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS image_text_raw TEXT",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION NOT NULL DEFAULT 0",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'DRAFT'",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS unit_cost_snapshot DOUBLE PRECISION NOT NULL DEFAULT 0",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS total_cost_snapshot DOUBLE PRECISION NOT NULL DEFAULT 0",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS movement_id INTEGER",
        "ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS confirmed_by TEXT",
    ]
    for s in stmts:
        try:
            cur.execute(s)
            print('OK:', s)
        except Exception as e:
            print('ERR:', s, e)
    try:
        conn.commit()
    except Exception:
        pass
    conn.close()

if __name__ == '__main__':
    main()
