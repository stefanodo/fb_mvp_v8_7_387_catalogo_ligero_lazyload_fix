#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT="$(cd "$DIR/.." && pwd)"
exec "$PARENT/NORMALIZAR_CATALOGO_UNIDADES_PRECIOS_PREPARACIONES.command" "$@"
