#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=============================================="
echo "System MAC · Normalizar catálogo"
echo "=============================================="
echo "Acciones:"
echo "- Pone unidad operativa kg en alimentos/líquidos."
echo "- Mantiene ud solo donde corresponde."
echo "- Recalcula precios 0 o no trazables como PRECIO_ESTIMADO."
echo "- Separa INSUMO / PREPARACIÓN."
echo "- Crea backup antes de tocar cada base."
echo ""
read -r -p "Escribe NORMALIZAR para continuar: " CONFIRM
if [ "$CONFIRM" != "NORMALIZAR" ]; then
  echo "Cancelado."
  exit 0
fi

PYTHON="python3"
SCRIPT="$DIR/tools/normalizar_catalogo_unidades_precios_preparaciones.py"
if [ ! -f "$SCRIPT" ]; then
  echo "No encuentro el script: $SCRIPT"
  exit 1
fi

DBS=(
  "$DIR/backend/runtime/fb_mvp_v8.db"
  "$DIR/backend/runtime/fb_copy.db"
  "$HOME/Documents/F&B_MAC_RUNTIME/fb_mvp_v8.db"
)

for DB in "${DBS[@]}"; do
  if [ -f "$DB" ]; then
    echo "Normalizando: $DB"
    "$PYTHON" "$SCRIPT" "$DB"
  else
    echo "No existe, omito: $DB"
  fi
done

echo ""
echo "Catálogo normalizado. Reinicia con REINICIAR_LIMPIO.command."
read -n 1 -s -r -p "Pulsa cualquier tecla para cerrar..."
echo ""
