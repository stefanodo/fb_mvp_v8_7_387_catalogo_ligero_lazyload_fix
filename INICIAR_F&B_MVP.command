#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

APP_DIR="$DIR/backend"
HOST="0.0.0.0"
PORT="8000"
URL="http://127.0.0.1:${PORT}"
RUNTIME_DB="${HOME}/Documents/F&B_MAC_RUNTIME/fb_mvp_v8.db"
RUNTIME_UPLOADS="${HOME}/Documents/F&B_MAC_RUNTIME/uploads"

safe_load_env_file() {
  local envfile="$1"
  if [ ! -f "$envfile" ]; then return 0; fi
  while IFS= read -r rawline || [ -n "$rawline" ]; do
    # Trim leading/trailing spaces
    line="$(printf '%s' "$rawline" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    case "$line" in
      ''|'#'*) continue ;;
    esac
    # Only KEY=VALUE lines. Ignore accidental pasted URLs or terminal text.
    if [[ "$line" != *=* ]]; then continue; fi
    key="${line%%=*}"
    val="${line#*=}"
    key="$(printf '%s' "$key" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    val="$(printf '%s' "$val" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then continue; fi
    # Strip matching quotes.
    if [[ "$val" == \"*\" && "$val" == *\" ]]; then val="${val:1:${#val}-2}"; fi
    if [[ "$val" == \'*\' && "$val" == *\' ]]; then val="${val:1:${#val}-2}"; fi
    export "$key=$val"
  done < "$envfile"
  echo "Configuración leída de forma segura: $envfile"
}

print_header() {
  echo "=============================================="
  echo " System MAC · Inicio único"
  echo "=============================================="
}

local_ip() {
  ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || ifconfig 2>/dev/null | awk '/inet / && $2 !~ /^127\./ {print $2; exit}' || true
}

start_server() {
  xattr -dr com.apple.quarantine "$DIR" 2>/dev/null || true
  chmod +x "$DIR"/*.command 2>/dev/null || true
  chmod +x "$DIR"/tools/*.command 2>/dev/null || true

  if [ ! -d "$APP_DIR" ]; then
    echo "ERROR: no encuentro backend en: $APP_DIR"
    echo "Descomprime el ZIP completo y abre este comando desde la carpeta descomprimida."
    read -n 1 -s -r -p "Pulsa cualquier tecla para cerrar..."
    exit 1
  fi

  safe_load_env_file "$DIR/.env"
  safe_load_env_file "$APP_DIR/.env"

  if [ -n "${OPENAI_API_KEY:-}" ] && [[ "${OPENAI_API_KEY}" == sk-* ]]; then
    export OPERATIVA_AI_MODE="${OPERATIVA_AI_MODE:-openai}"
    export OPERATIVA_STT_MODE="${OPERATIVA_STT_MODE:-openai}"
    export OPERATIVA_AI_MODEL="${OPERATIVA_AI_MODEL:-gpt-4o-mini}"
    export OPERATIVA_STT_MODEL="${OPERATIVA_STT_MODEL:-gpt-4o-mini-transcribe}"
  else
    unset OPENAI_API_KEY 2>/dev/null || true
    export OPERATIVA_AI_MODE="${OPERATIVA_AI_MODE:-local}"
    export OPERATIVA_STT_MODE="${OPERATIVA_STT_MODE:-local}"
  fi

  LOCAL_IP="$(local_ip)"
  LOCAL_HOSTNAME="$(scutil --get LocalHostName 2>/dev/null || hostname -s 2>/dev/null || echo Mac)"
  if [ -n "$LOCAL_IP" ]; then LAN_URL="http://${LOCAL_IP}:${PORT}"; else LAN_URL="http://${LOCAL_HOSTNAME}.local:${PORT}"; fi
  BONJOUR_URL="http://${LOCAL_HOSTNAME}.local:${PORT}"
  export FB_LAN_URL="$LAN_URL"
  export FB_BONJOUR_URL="$BONJOUR_URL"
  export FB_SERVER_HOST="$HOST"
  export FB_SERVER_PORT="$PORT"

  mkdir -p "$(dirname "$RUNTIME_DB")" "$RUNTIME_UPLOADS"

  if lsof -iTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Puerto ${PORT} en uso. Cierro servidor anterior..."
    PIDS="$(lsof -tiTCP:${PORT} -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$PIDS" ]; then echo "$PIDS" | xargs kill -TERM 2>/dev/null || true; sleep 2; fi
    if lsof -iTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
      PIDS="$(lsof -tiTCP:${PORT} -sTCP:LISTEN 2>/dev/null || true)"
      if [ -n "$PIDS" ]; then echo "$PIDS" | xargs kill -9 2>/dev/null || true; sleep 1; fi
    fi
  fi

  cd "$APP_DIR"
  python3 -m ensurepip --upgrade >/dev/null 2>&1 || true
  python3 -m pip install --user --upgrade pip >/dev/null 2>&1 || true
  python3 -m pip install --user -r requirements.txt || {
    echo "No se pudieron instalar todas las dependencias, pruebo con las disponibles..."
    python3 - <<'PYCHK' || exit 1
import fastapi, uvicorn, jinja2
PYCHK
  }
  cd "$DIR"

  cat > "$DIR/ABRIR_DESDE_MOVIL.txt" <<TXT
System MAC · Acceso móvil

Mac:   ${URL}
Móvil: ${LAN_URL}
Alt.:  ${BONJOUR_URL}

Mantén esta ventana de Terminal abierta.
TXT

  echo ""
  print_header
  echo "Mac:    ${URL}"
  echo "Móvil:  ${LAN_URL}"
  echo "Alt.:   ${BONJOUR_URL}"
  echo "Base activa: $RUNTIME_DB"
  echo "IA: ${OPERATIVA_AI_MODE:-local} | Voz: ${OPERATIVA_STT_MODE:-local} | Texto: ${OPERATIVA_AI_MODEL:-local} | STT: ${OPERATIVA_STT_MODEL:-local}"
  echo ""
  if [ -f "$RUNTIME_DB" ]; then
    python3 - <<PYDB || true
import sqlite3
from pathlib import Path
p=Path(r"$RUNTIME_DB")
con=sqlite3.connect(p); cur=con.cursor()
for t in ["movements","orders","productions"]:
    try: print(f"{t}: {cur.execute('select count(*) from '+t).fetchone()[0]}")
    except Exception: pass
con.close()
PYDB
  fi
  echo ""
  echo "Abro Safari. Mantén esta ventana abierta mientras uses la app."
  echo ""

  python3 -m uvicorn app.main:app --host ${HOST} --port ${PORT} --app-dir "$APP_DIR" &
  SERVER_PID=$!
  cleanup() { if kill -0 "$SERVER_PID" >/dev/null 2>&1; then kill "$SERVER_PID" >/dev/null 2>&1 || true; fi; }
  trap cleanup EXIT INT TERM

  OPENED=0
  for i in $(seq 1 60); do
    if python3 - <<PY2 >/dev/null 2>&1
import urllib.request
urllib.request.urlopen('${URL}', timeout=1)
PY2
    then
      open -a Safari "${URL}/movil" >/dev/null 2>&1 || open "${URL}/movil" >/dev/null 2>&1 || true
      OPENED=1
      echo "Servidor listo. Móvil: ${LAN_URL}"
      break
    fi
    sleep 1
  done
  if [ "$OPENED" -eq 0 ]; then
    echo "Servidor arrancado. Abre: ${URL}/movil"
  fi
  wait "$SERVER_PID"
}

start_server
