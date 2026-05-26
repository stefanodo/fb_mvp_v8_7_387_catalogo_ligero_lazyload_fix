#!/usr/bin/env python3
import os, sqlite3, shutil, datetime, sys

DB_PATH = os.environ.get('SYSTEM_MAC_RUNTIME_DB') or os.path.expanduser('~/Documents/F&B_MAC_RUNTIME/fb_mvp_v8.db')

def fix_db(db_path: str):
    if not os.path.exists(db_path):
        print(f'No existe la base activa: {db_path}')
        return 1
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = db_path + f'.bak_minmax_kg_{stamp}'
    shutil.copy2(db_path, backup)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    total = 0
    examples = []
    def norm(v):
        try: x = float(v or 0.0)
        except Exception: return 0.0
        return x/1000.0 if abs(x) >= 1000.0 else x
    for r in cur.execute("SELECT id,name,unit,min_qty,max_qty FROM items WHERE lower(COALESCE(unit,''))='kg' AND (abs(COALESCE(min_qty,0))>=1000 OR abs(COALESCE(max_qty,0))>=1000)").fetchall():
        old=(float(r['min_qty'] or 0), float(r['max_qty'] or 0)); new=(norm(r['min_qty']), norm(r['max_qty']))
        cur.execute('UPDATE items SET min_qty=?, max_qty=? WHERE id=?', (new[0], new[1], int(r['id'])))
        total += 1
        if len(examples)<8: examples.append(f"ART {r['name']}: {old} -> {new} kg")
    for r in cur.execute("""
        SELECT lp.id, i.name, i.unit, lp.min_qty, lp.max_qty, w.name warehouse_name
          FROM item_location_prefs lp
          JOIN items i ON i.id=lp.item_id
          JOIN warehouses w ON w.id=lp.warehouse_id
         WHERE lower(COALESCE(i.unit,''))='kg'
           AND (abs(COALESCE(lp.min_qty,0))>=1000 OR abs(COALESCE(lp.max_qty,0))>=1000)
    """).fetchall():
        old=(float(r['min_qty'] or 0), float(r['max_qty'] or 0)); new=(norm(r['min_qty']), norm(r['max_qty']))
        cur.execute('UPDATE item_location_prefs SET min_qty=?, max_qty=? WHERE id=?', (new[0], new[1], int(r['id'])))
        total += 1
        if len(examples)<8: examples.append(f"PREF {r['name']} / {r['warehouse_name']}: {old} -> {new} kg")
    con.commit()
    # verificación
    bad = cur.execute("""
        SELECT COUNT(*) c
          FROM item_location_prefs lp JOIN items i ON i.id=lp.item_id
         WHERE lower(COALESCE(i.unit,''))='kg' AND (abs(COALESCE(lp.min_qty,0))>=1000 OR abs(COALESCE(lp.max_qty,0))>=1000)
    """).fetchone()['c']
    bad += cur.execute("SELECT COUNT(*) c FROM items WHERE lower(COALESCE(unit,''))='kg' AND (abs(COALESCE(min_qty,0))>=1000 OR abs(COALESCE(max_qty,0))>=1000)").fetchone()['c']
    con.close()
    print('Base corregida:', db_path)
    print('Backup:', backup)
    print('Registros corregidos:', total)
    for ex in examples: print('-', ex)
    print('Valores kg >=1000 restantes:', bad)
    return 0 if bad == 0 else 2

if __name__ == '__main__':
    sys.exit(fix_db(DB_PATH))
