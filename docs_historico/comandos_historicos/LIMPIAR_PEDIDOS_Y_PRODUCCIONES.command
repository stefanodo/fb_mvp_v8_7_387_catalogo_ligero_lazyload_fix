#!/bin/bash
set -e
cd "$(dirname "$0")"
APP_ROOT="$PWD"
DBS=("backend/runtime/fb_mvp_v8.db" "backend/runtime/fb_copy.db")
echo "============================================"
echo "System MAC · Limpiar pedidos y producciones"
echo "============================================"
echo "Se dejarán en blanco pedidos, producciones y cola operativa."
echo "No se toca stock, recetas, artículos, albaranes, mermas ni inventario."
echo ""
read -p "Escribe LIMPIAR para continuar: " CONF
if [ "$CONF" != "LIMPIAR" ]; then
  echo "Cancelado."
  exit 0
fi
python3 - <<'PY'
import sqlite3, os
from pathlib import Path
root=Path.cwd()
dbs=[root/'backend/runtime/fb_mvp_v8.db', root/'backend/runtime/fb_copy.db']
for dbp in dbs:
    if not dbp.exists():
        continue
    conn=sqlite3.connect(dbp)
    cur=conn.cursor()
    tables=[r[0] for r in cur.execute("select name from sqlite_master where type='table'")]
    # Operativa rápida / carritos / colas
    for t in ['operational_queue_contributions','operational_queue_items']:
        if t in tables: cur.execute(f'DELETE FROM {t}')
    # Pedidos
    if 'order_lines' in tables: cur.execute('DELETE FROM order_lines')
    if 'orders' in tables: cur.execute('DELETE FROM orders')
    # Producciones
    if 'production_lines' in tables: cur.execute('DELETE FROM production_lines')
    if 'productions' in tables: cur.execute('DELETE FROM productions')
    # Reinicio de secuencias, si existen
    try:
        for t in ['operational_queue_contributions','operational_queue_items','order_lines','orders','production_lines','productions']:
            cur.execute('DELETE FROM sqlite_sequence WHERE name=?',(t,))
    except Exception:
        pass
    conn.commit(); conn.close()
    print(f'OK limpio: {dbp}')
print('Listo. Abre DESBLOQUEAR_y_INICIAR.command o INICIAR_HTTPS_TEMPORAL.command.')
PY
read -n 1 -s -r -p "Pulsa cualquier tecla para cerrar..."
echo
