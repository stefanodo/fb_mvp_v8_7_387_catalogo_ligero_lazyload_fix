#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

xattr -dr com.apple.quarantine "$DIR" 2>/dev/null || true
chmod +x "$DIR"/*.command 2>/dev/null || true

echo "=============================================="
echo " System MAC · Poner base operativa a cero"
echo "=============================================="
echo "Esto limpia STOCK operativo, PEDIDOS, PRODUCCIONES y colas de operativa."
echo "No borra recetas, catálogo, proveedores, albaranes históricos ni mermas."
echo "Crea backup antes de tocar cada base."
echo ""
read -p "Escribe CERO para continuar: " CONF
if [ "$CONF" != "CERO" ]; then
  echo "Cancelado."
  exit 0
fi

python3 - <<'PY'
import sqlite3, shutil, time, os
from pathlib import Path
root=Path.cwd()
home=Path.home()
paths=[]
# Bases incluidas en ZIP
for rel in ['backend/runtime/fb_mvp_v8.db','backend/runtime/fb_copy.db']:
    paths.append(root/rel)
# Base real compartida usada por la app en Mac
paths.append(home/'Documents'/'F&B_MAC_RUNTIME'/'fb_mvp_v8.db')
seen=set()
now=time.strftime('%Y%m%d_%H%M%S')
for dbp in paths:
    dbp=Path(dbp)
    key=str(dbp.resolve()) if dbp.exists() else str(dbp)
    if key in seen or not dbp.exists():
        continue
    seen.add(key)
    backup=dbp.with_name(dbp.stem + f'_backup_pre_cero_{now}' + dbp.suffix)
    shutil.copy2(dbp, backup)
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

    deleted={}
    for t in ['operational_queue_contributions','operational_queue_items','order_lines','orders','production_lines','productions','movements']:
        if table_exists(cur, t):
            try:
                deleted[t]=cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                cur.execute(f'DELETE FROM {t}')
            except Exception as exc:
                deleted[t]=f'ERROR {exc}'
    # Reset sqlite_sequence entries if present (sqlite only)
    try:
        for t in ['operational_queue_contributions','operational_queue_items','order_lines','orders','production_lines','productions','movements']:
            try:
                cur.execute('DELETE FROM sqlite_sequence WHERE name=?',(t,))
            except Exception:
                pass
    except Exception:
        pass
    conn.commit()
    # Verificación
    checks={}
    for t in ['movements','orders','order_lines','productions','production_lines']:
        if t in tables:
            checks[t]=cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    conn.close()
    print(f'OK base a cero: {dbp}')
    print(f'Backup: {backup}')
    print(f'Eliminado antes: {deleted}')
    print(f'Verificación: {checks}')
print('Listo. Abre REINICIAR_LIMPIO.command o DESBLOQUEAR_y_INICIAR.command.')
PY

read -n 1 -s -r -p "Pulsa cualquier tecla para cerrar..."
echo
