#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

xattr -dr com.apple.quarantine "$DIR" 2>/dev/null || true
chmod +x "$DIR"/*.command 2>/dev/null || true

APP_DIR="$DIR/backend"
PORT="8000"
HOST="0.0.0.0"
LOCAL_URL="http://127.0.0.1:${PORT}"
RUNTIME_DIR="$APP_DIR/runtime"
TOOLS_DIR="$DIR/tools"
mkdir -p "$RUNTIME_DIR" "$TOOLS_DIR"

# Carga .env sin mostrar claves.
load_env_file() {
  local envfile="$1"
  if [ -f "$envfile" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$envfile"
    set +a
    echo "Configuración cargada: $envfile"
  fi
}
load_env_file "$DIR/.env"
load_env_file "$APP_DIR/.env"

if [ -n "${OPENAI_API_KEY:-}" ]; then
  export OPERATIVA_AI_MODE="${OPERATIVA_AI_MODE:-openai}"
  export OPERATIVA_STT_MODE="${OPERATIVA_STT_MODE:-openai}"
  export OPERATIVA_AI_MODEL="${OPERATIVA_AI_MODEL:-gpt-4o-mini}"
  export OPERATIVA_STT_MODEL="${OPERATIVA_STT_MODEL:-gpt-4o-mini-transcribe}"
else
  export OPERATIVA_AI_MODE="${OPERATIVA_AI_MODE:-local}"
  export OPERATIVA_STT_MODE="${OPERATIVA_STT_MODE:-local}"
fi

find_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    command -v cloudflared
    return 0
  fi
  if [ -x "$TOOLS_DIR/cloudflared" ]; then
    echo "$TOOLS_DIR/cloudflared"
    return 0
  fi
  return 1
}

install_cloudflared() {
  echo "No encuentro cloudflared. Intento instalarlo automáticamente para crear HTTPS temporal."
  if command -v brew >/dev/null 2>&1; then
    echo "Instalando con Homebrew: cloudflared"
    brew install cloudflared || true
    if command -v cloudflared >/dev/null 2>&1; then return 0; fi
  fi
  echo "Descargando cloudflared portable..."
  ARCH="$(uname -m)"
  if [ "$ARCH" = "arm64" ]; then
    URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz"
  else
    URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz"
  fi
  TMP_TGZ="$RUNTIME_DIR/cloudflared.tgz"
  rm -f "$TMP_TGZ"
  curl -L --fail "$URL" -o "$TMP_TGZ"
  tar -xzf "$TMP_TGZ" -C "$TOOLS_DIR"
  chmod +x "$TOOLS_DIR/cloudflared" 2>/dev/null || true
  if [ ! -x "$TOOLS_DIR/cloudflared" ]; then
    echo "No se pudo instalar cloudflared. Revisa conexión a internet o instala cloudflared manualmente."
    exit 1
  fi
}

if ! CLOUDFLARED_BIN="$(find_cloudflared)"; then
  install_cloudflared
  CLOUDFLARED_BIN="$(find_cloudflared)"
fi

echo "Usando cloudflared: $CLOUDFLARED_BIN"

# Comprueba/instala dependencias antes de arrancar.
cd "$APP_DIR"
python3 -m ensurepip --upgrade >/dev/null 2>&1 || true
python3 -m pip install --user --upgrade pip >/dev/null 2>&1 || true
python3 -m pip install --user -r requirements.txt || {
  echo "No se pudieron instalar todas las dependencias automáticamente. Intento continuar si FastAPI/Uvicorn existen."
  python3 - <<'PYCHK' || exit 1
import fastapi, uvicorn, jinja2
PYCHK
}
cd "$DIR"

# Arranca túnel primero para obtener URL HTTPS pública temporal.
TUNNEL_LOG="$RUNTIME_DIR/cloudflared_https.log"
rm -f "$TUNNEL_LOG"
"$CLOUDFLARED_BIN" tunnel --url "$LOCAL_URL" --no-autoupdate >"$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

cleanup() {
  if [ -n "${SERVER_PID:-}" ] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then kill "$SERVER_PID" >/dev/null 2>&1 || true; fi
  if kill -0 "$TUNNEL_PID" >/dev/null 2>&1; then kill "$TUNNEL_PID" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT INT TERM

TUNNEL_URL=""
for i in $(seq 1 45); do
  TUNNEL_URL="$(grep -Eo 'https://[-a-zA-Z0-9.]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -1 || true)"
  if [ -n "$TUNNEL_URL" ]; then break; fi
  sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
  echo "No pude crear el túnel HTTPS temporal. Log:"
  tail -80 "$TUNNEL_LOG" || true
  exit 1
fi

export FB_PUBLIC_HTTPS_URL="$TUNNEL_URL"
export FB_LAN_URL="$TUNNEL_URL"
export FB_SERVER_HOST="$HOST"
export FB_SERVER_PORT="$PORT"

cat > "$DIR/ABRIR_HTTPS_TEMPORAL.txt" <<TXT
System MAC · Acceso HTTPS temporal

Abre este enlace desde el móvil:
$TUNNEL_URL

Operativa rápida:
$TUNNEL_URL/?page=operativa

Este enlace es temporal y público mientras esta ventana esté abierta.
No lo compartas fuera de tu equipo.
TXT

cat > "$DIR/ABRIR_HTTPS_TEMPORAL.html" <<HTML
<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>System MAC · HTTPS temporal</title><style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#101010;color:#fff;padding:28px;line-height:1.35}.card{max-width:720px;margin:auto;background:#1b1b1b;border:1px solid #3b3020;border-radius:24px;padding:26px}.tag{display:inline-block;background:#f2c45b;color:#111;font-weight:900;border-radius:999px;padding:8px 14px}.url{font-size:24px;font-weight:900;color:#f2c45b;word-break:break-all}.btn{display:inline-block;background:#f2c45b;color:#111;font-weight:900;text-decoration:none;border-radius:16px;padding:14px 18px;margin:8px 8px 8px 0}.warn{margin-top:14px;background:#361b1b;border:1px solid #7a3b3b;border-radius:16px;padding:12px;color:#ffdede}.muted{color:#cfcfcf}</style></head><body><div class="card"><div class="tag">HTTPS temporal activo</div><h1>System MAC</h1><p class="muted">Usa este enlace en el móvil para probar micrófono/audio real. Mantén abierta la ventana de Terminal.</p><p class="url">$TUNNEL_URL</p><a class="btn" href="$TUNNEL_URL/?page=operativa">Abrir Operativa</a><a class="btn" href="$TUNNEL_URL/movil">Ver QR</a><div class="warn">Este enlace es temporal y público mientras la Terminal esté abierta. No lo compartas fuera de tu equipo.</div></div></body></html>
HTML

if lsof -iTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
  echo "El puerto ${PORT} ya está en uso. Usaré el servidor ya arrancado si responde."
  SERVER_PID=""
else
  python3 -m uvicorn app.main:app --host ${HOST} --port ${PORT} --app-dir "$APP_DIR" &
  SERVER_PID=$!
fi

echo ""
echo "=============================================="
echo " System MAC · HTTPS temporal para móvil"
echo "=============================================="
echo "Mac local:      $LOCAL_URL"
echo "Móvil HTTPS:    $TUNNEL_URL"
echo "Operativa:      $TUNNEL_URL/?page=operativa"
echo "IA operativa:   ${OPERATIVA_AI_MODE:-local} | STT voz: ${OPERATIVA_STT_MODE:-local} | Texto: ${OPERATIVA_AI_MODEL:-local} | Voz: ${OPERATIVA_STT_MODEL:-local}"
echo ""
echo "Mantén esta ventana abierta. Al cerrarla, se cierra el enlace HTTPS temporal."
echo ""

# Espera a que app responda y abre página QR/operativa.
OPENED=0
for i in $(seq 1 60); do
  if python3 - <<PY2 >/dev/null 2>&1
import urllib.request
urllib.request.urlopen('$LOCAL_URL', timeout=1)
PY2
  then
    if [ "$OPENED" -eq 0 ]; then
      open "$TUNNEL_URL/movil" >/dev/null 2>&1 || true
      OPENED=1
      echo "Listo. En el móvil abre: $TUNNEL_URL/?page=operativa"
    fi
    break
  fi
  sleep 1
done

# Mantiene vivos servidor y túnel.
if [ -n "${SERVER_PID:-}" ]; then
  wait "$SERVER_PID"
else
  wait "$TUNNEL_PID"
fi
