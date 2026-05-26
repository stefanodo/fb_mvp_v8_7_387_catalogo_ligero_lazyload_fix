#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "System MAC · Corregir Min/Max kg"
echo "Corrige valores heredados tipo 20000 kg -> 20 kg en la base activa."
RUNTIME_DB="$HOME/Documents/F&B_MAC_RUNTIME/fb_mvp_v8.db"
if [ -f "$RUNTIME_DB" ]; then
  export SYSTEM_MAC_RUNTIME_DB="$RUNTIME_DB"
else
  export SYSTEM_MAC_RUNTIME_DB="$PWD/backend/runtime/fb_mvp_v8.db"
fi
python3 tools/corregir_minmax_kg.py
echo "Proceso completado. Reinicia con ABRIR_SYSTEM_MAC.command"
read -n 1 -s -r -p "Pulsa cualquier tecla para cerrar..."
