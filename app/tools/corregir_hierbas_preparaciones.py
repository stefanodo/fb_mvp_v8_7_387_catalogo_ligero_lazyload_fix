#!/usr/bin/env python3
import sqlite3, sys, shutil, re, unicodedata, datetime
from pathlib import Path

DB = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path('backend/runtime/fb_mvp_v8.db')
if not DB.exists():
    print(f'No existe la base: {DB}')
    sys.exit(1)
backup = DB.with_suffix(DB.suffix + f'.backup_hierbas_preparaciones_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}')
shutil.copy2(DB, backup)
print(f'Backup creado: {backup}')

def norm(v):
    s = unicodedata.normalize('NFD', str(v or '').upper())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^A-Z0-9]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

herbs = {
    'ALBAHACA': 1.80, 'CILANTRO': 1.50, 'CEBOLLINO': 1.60, 'MENTA': 1.80,
    'PEREJIL': 0.80, 'HIERBABUENA': 1.80, 'ENELDO': 1.80, 'ROMERO': 1.60,
    'TOMILLO': 1.60, 'CEBOLLETA': 1.20,
}
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()
cols = {r['name'] for r in cur.execute('PRAGMA table_info(items)').fetchall()}
changed = 0
for r in cur.execute('SELECT id,name FROM items').fetchall():
    n = norm(r['name'])
    if n in herbs:
        sets = ['unit=?','stock_area=?','order_category=?','item_type=?','current_price=?']
        vals = ['manojo','FRESCOS','verduras','INSUMO',herbs[n]]
        extras = {
            'price_status':'PRECIO_ESTIMADO','price_source':'MERCADO_ESTIMADO_ESP_2025_2026',
            'price_confidence':'media','price_reference_year':'2025/2026',
            'price_operational_unit':'manojo','price_operational_value':herbs[n],
            'price_notes':'Hierba fresca operativa por manojo. Validar precio con proveedor/albarán.',
        }
        for k,v in extras.items():
            if k in cols:
                sets.append(f'{k}=?'); vals.append(v)
        vals.append(int(r['id']))
        cur.execute(f"UPDATE items SET {', '.join(sets)} WHERE id=?", vals)
        changed += 1
    if n in {'AGUACHILE','AGUACHILES'} or n.startswith('AGUACHILE'):
        sets = ['unit=?','stock_area=?','order_category=?','item_type=?']
        vals = ['kg','PREPARACIONES','preparaciones','PREPARACION']
        for k,v in {'price_status':'PRECIO_ESTIMADO','price_source':'COSTE_PREPARACION_ESTIMADO','price_confidence':'baja','price_operational_unit':'kg','price_notes':'Preparación/subreceta. No mostrar como insumo de compra manual.'}.items():
            if k in cols:
                sets.append(f'{k}=?'); vals.append(v)
        vals.append(int(r['id']))
        cur.execute(f"UPDATE items SET {', '.join(sets)} WHERE id=?", vals)
        changed += 1
con.commit(); con.close()
print(f'Correcciones aplicadas: {changed}')
