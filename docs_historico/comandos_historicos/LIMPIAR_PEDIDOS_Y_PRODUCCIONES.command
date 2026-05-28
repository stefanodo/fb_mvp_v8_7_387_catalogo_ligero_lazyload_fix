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

    def table_exists(cur, name):
        try:
            cur.execute(f"PRAGMA table_info({name})")
            return cur.fetchone() is not None
        except Exception:
            try:
                cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name=%s", (name,))
                return cur.fetchone() is not None
            except Exception:
                return False

    # Operativa rápida / carritos / colas
    for t in ['operational_queue_contributions','operational_queue_items']:
        if table_exists(cur, t):
            try:
                cur.execute(f'DELETE FROM {t}')
            except Exception:
                pass

    # Pedidos
    for t in ['order_lines','orders']:
        if table_exists(cur, t):
            try:
                cur.execute(f'DELETE FROM {t}')
            except Exception:
                pass

    # Producciones
    for t in ['production_lines','productions']:
        if table_exists(cur, t):
            try:
                cur.execute(f'DELETE FROM {t}')
            except Exception:
                pass

    # Reinicio de secuencias, si existen (sqlite only)
    try:
        for t in ['operational_queue_contributions','operational_queue_items','order_lines','orders','production_lines','productions']:
            try:
                cur.execute('DELETE FROM sqlite_sequence WHERE name=?',(t,))
            except Exception:
                pass
    except Exception:
        pass

    conn.commit(); conn.close()
    print(f'OK limpio: {dbp}')
print('Listo. Abre DESBLOQUEAR_y_INICIAR.command o INICIAR_HTTPS_TEMPORAL.command.')
PY
read -n 1 -s -r -p "Pulsa cualquier tecla para cerrar..."
echo
