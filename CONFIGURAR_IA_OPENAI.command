#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=============================================="
echo " System MAC · Configurar IA de Operativa"
echo "=============================================="
echo ""
echo "Necesitas una API Key de OpenAI. No se muestra mientras escribes."
echo "Puedes crearla desde el dashboard oficial de OpenAI."
echo ""
read -s -p "Pega aquí tu OPENAI_API_KEY: " OPENAI_KEY
echo ""
if [ -z "${OPENAI_KEY}" ]; then
  echo "No se ha escrito ninguna clave. No cambio la configuración."
  exit 1
fi

cat > "$DIR/.env" <<ENV
# System MAC · IA Operativa
# Archivo creado por CONFIGURAR_IA_OPENAI.command
OPERATIVA_AI_MODE=openai
OPERATIVA_STT_MODE=openai
OPENAI_API_KEY=${OPENAI_KEY}
OPERATIVA_AI_MODEL=gpt-4o-mini
OPERATIVA_STT_MODEL=gpt-4o-mini-transcribe
OPERATIVA_AI_TIMEOUT=12
OPERATIVA_STT_TIMEOUT=25
ENV
chmod 600 "$DIR/.env" 2>/dev/null || true

if [ -d "$DIR/backend" ]; then
  cp "$DIR/.env" "$DIR/backend/.env"
  chmod 600 "$DIR/backend/.env" 2>/dev/null || true
fi

echo ""
echo "IA configurada. Reinicia la aplicación con DESBLOQUEAR_y_INICIAR.command."
echo ""
echo "Modo texto:  openai / gpt-4o-mini"
echo "Modo voz:    openai / gpt-4o-mini-transcribe"
echo ""
read -n 1 -s -r -p "Pulsa cualquier tecla para cerrar..."
echo ""
