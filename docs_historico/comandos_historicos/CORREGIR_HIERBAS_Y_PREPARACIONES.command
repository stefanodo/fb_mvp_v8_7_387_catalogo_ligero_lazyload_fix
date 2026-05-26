#!/bin/bash
cd "$(dirname "$0")"
python3 tools/corregir_hierbas_preparaciones.py "$HOME/Documents/F&B_MAC_RUNTIME/fb_mvp_v8.db"
echo ""
echo "Listo. Cierra y abre ABRIR_SYSTEM_MAC.command para ver los cambios."
read -n 1 -s -r -p "Pulsa cualquier tecla para cerrar..."
