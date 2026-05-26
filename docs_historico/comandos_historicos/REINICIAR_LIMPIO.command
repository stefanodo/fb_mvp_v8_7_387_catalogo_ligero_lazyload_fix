#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="8000"

echo "=============================================="
echo " System MAC · Reinicio limpio"
echo "=============================================="

xattr -dr com.apple.quarantine "$DIR" 2>/dev/null || true
chmod +x "$DIR"/*.command 2>/dev/null || true

if lsof -iTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Cerrando procesos activos en el puerto ${PORT}..."
  PIDS="$(lsof -tiTCP:${PORT} -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$PIDS" ]; then
    echo "$PIDS" | xargs kill -TERM 2>/dev/null || true
    sleep 2
  fi
fi
if lsof -iTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Forzando cierre del puerto ${PORT}..."
  PIDS="$(lsof -tiTCP:${PORT} -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$PIDS" ]; then
    echo "$PIDS" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
fi

echo "Arrancando System MAC..."
exec /bin/bash "$DIR/DESBLOQUEAR_y_INICIAR.command"
