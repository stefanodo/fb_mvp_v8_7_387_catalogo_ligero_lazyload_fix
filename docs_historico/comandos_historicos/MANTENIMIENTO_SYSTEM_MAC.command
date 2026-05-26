#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
xattr -dr com.apple.quarantine "$DIR" 2>/dev/null || true
chmod +x "$DIR"/*.command 2>/dev/null || true

clear || true
echo "=============================================="
echo " System MAC · Mantenimiento"
echo "=============================================="
echo "1) Configurar IA / OpenAI"
echo "2) Poner stock, pedidos y producciones a cero"
echo "3) Normalizar catálogo, unidades, precios y preparaciones"
echo "4) Limpiar solo pedidos y producciones"
echo "5) Corregir Min/Max kg heredado (20000 -> 20 kg)"
echo "6) Corregir hierbas por manojo y preparaciones"
echo "7) Iniciar HTTPS temporal Cloudflare (opcional)"
echo "8) Salir"
echo ""
read -r -p "Elige opción [1-8]: " opt
case "$opt" in
  1) exec /bin/bash "$DIR/CONFIGURAR_IA_OPENAI.command" ;;
  2) exec /bin/bash "$DIR/PONER_STOCK_PEDIDOS_PRODUCCIONES_A_CERO.command" ;;
  3) exec /bin/bash "$DIR/NORMALIZAR_CATALOGO_UNIDADES_PRECIOS_PREPARACIONES.command" ;;
  4) exec /bin/bash "$DIR/LIMPIAR_PEDIDOS_Y_PRODUCCIONES.command" ;;
  5) exec /bin/bash "$DIR/CORREGIR_MINMAX_KG.command" ;;
  6) exec /bin/bash "$DIR/CORREGIR_HIERBAS_Y_PREPARACIONES.command" ;;
  7) exec /bin/bash "$DIR/INICIAR_HTTPS_TEMPORAL.command" ;;
  *) echo "Cerrado."; exit 0 ;;
esac
